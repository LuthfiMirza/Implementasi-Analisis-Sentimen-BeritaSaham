<?php

namespace App\Services\Trading;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\SelfRadarSignalLog;
use App\Services\MarketData\LiveMarketDataService;
use Carbon\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * Fase DB: "Signal Radar" -- estimasi LIVE seberapa dekat tiap ticker x strategi ke threshold
 * sinyal resmi, dipakai halaman /trades/radar. BUKAN sinyal resmi -- sinyal resmi tetap cuma
 * lahir dari quant/drawdown_bounce_tracker/detect_signal.py yang jalan closing 15:18 WIB
 * (research:detect-drawdown-bounce-signal). Service ini murni "heads-up" pakai harga BERJALAN
 * sebagai hipotetis closing hari ini -- bisa berubah sampai closing beneran.
 *
 * WAJIB konsisten dgn formula Python (rumus RSI EWM/Wilder, bukan simple-average seperti
 * FeatureBuilderService::rsi() -- itu dipakai buat fitur model prediksi, beda tujuan/beda angka).
 * Kalau radar pakai formula RSI yang beda dari detect_signal.py, "jarak ke trigger" yang
 * ditampilkan bisa menyesatkan (persis kelas bug yang sudah pernah kejadian nyata -- lihat
 * komentar Fase BY di detect_signal.py soal window-sensitivity RSI rekursif).
 */
class SignalRadarService
{
    // Fase DC: SAMA PERSIS `GABUNGAN_SCAN_TICKERS` di detect_signal.py -- gap lama (TINS/PTRO/
    // ENRG/RAJA terdaftar di COMBINED_RULE_TICKERS python tapi TIDAK PERNAH benar-benar di-scan
    // detect()) sudah DIPERBAIKI di Python (ticker baru diaktifkan mulai 2026-08-26, per-ticker
    // start-date guard spt DSSA MOMENTUM -- supaya sinyal historis yg kelewat, mis. ENRG/RAJA
    // 11-18 Agu, TIDAK backdate jadi alert Telegram + trade palsu). Radar ikut nambah 4 ticker
    // ini SEKARANG karena scan resminya SUDAH benar-benar mencakup mereka mulai hari ini.
    //
    // Fase DU: INET ditambahkan -- screening lanjutan pick "Paper To Billion" (Fase DR/DS/DU),
    // n=21 episode, win rate 47.6%, avg +1.89%, konsisten discovery/holdout, lolos filter
    // likuiditas Rp100M/hari (rata-rata Rp145M). Lihat detect_signal.py utk detail lengkap +
    // kandidat lain (MGLV) yg ditolak murni krn likuiditas walau statistiknya lebih kuat.
    private const GABUNGAN_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'TINS', 'PTRO', 'ENRG', 'RAJA', 'INET'];

    private const MOMENTUM_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'DSSA'];

    private const BOTTOM_REBOUND_TICKERS = ['BUMI', 'DEWA'];

    private const SELF_RADAR_TICKERS = ['BAJA', 'MCAS', 'GDST', 'MDIA', 'BYAN', 'PACK', 'KOTA', 'MGLV', 'SLIS', 'FAST', 'TEBE', 'IATA', 'JGLE', 'KIJA', 'SINI', 'GULA', 'JKON', 'JARR', 'INET', 'NSSS', 'DEWA', 'ISAT', 'CUAN', 'PADA', 'WIFI', 'SSIA', 'HATM', 'ESSA', 'BRMS', 'FPNI'];

    // Ticker yg leg drawdown_20d berlaku -- SAMA PERSIS COMBINED_RULE_TICKERS python (9 ticker,
    // SMGR sengaja TIDAK termasuk -- gagal gate P4 validasi ketat, tetap ret_2d saja).
    private const DRAWDOWN_LEG_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'ESSA', 'UNVR', 'TINS', 'PTRO', 'ENRG', 'RAJA'];

    private const DROP_THRESHOLD = -0.05;       // ret_2d, sama persis DROP_THRESHOLD python

    private const DRAWDOWN_THRESHOLD = -0.20;   // dd_20d, sama persis DRAWDOWN_THRESHOLD python

    private const MOMENTUM_RSI_THRESHOLD = 60.0; // sama persis MOMENTUM_RSI_THRESHOLD python

    private const BOTTOM_REBOUND_THRESHOLD = 0.05; // sama persis BOTTOM_REBOUND_THRESHOLD python

    private const SELF_RADAR_RSI_MIN = 60.0;

    private const SELF_RADAR_RET_5D_MIN = 0.05;

    private const SELF_RADAR_DD_20D_MIN = -0.05;

    public function __construct(private LiveMarketDataService $liveMarketData) {}

    /**
     * @return array{gabungan: array, momentum: array, bottom_rebound: array, self_radar: array, generated_at: string}
     */
    public function build(): array
    {
        $allTickers = collect(self::GABUNGAN_TICKERS)
            ->merge(self::MOMENTUM_TICKERS)
            ->merge(self::BOTTOM_REBOUND_TICKERS)
            ->merge(self::SELF_RADAR_TICKERS)
            ->unique()->sort()->values();

        $gabungan = [];
        $momentum = [];
        $bottomRebound = [];
        $selfRadar = [];

        $stocks = Stock::whereIn('code', $allTickers)->get()->keyBy('code');

        foreach ($allTickers as $ticker) {
            $stock = $stocks->get($ticker);
            $series = $this->historicalSeries($ticker, $stock); // closes ending KEMARIN (hari ini di-exclude eksplisit)
            if (count($series) < 25) {
                continue; // data historis belum cukup utk RSI/dd_20d/bottom_10d
            }

            $livePrice = $stock ? $this->livePrice($stock) : null;
            if ($livePrice === null) {
                continue; // tanpa harga live, tidak bisa hitung estimasi -- skip diam-diam, bukan tampilkan angka palsu
            }

            $combined = array_merge($series, [$livePrice]); // hipotetis "closing hari ini"

            if (in_array($ticker, self::GABUNGAN_TICKERS, true)) {
                $gabungan[] = $this->buildGabunganRow($ticker, $livePrice, $combined);
            }
            if (in_array($ticker, self::MOMENTUM_TICKERS, true)) {
                $momentum[] = $this->buildMomentumRow($ticker, $livePrice, $combined);
            }
            if (in_array($ticker, self::BOTTOM_REBOUND_TICKERS, true)) {
                $bottomRebound[] = $this->buildBottomReboundRow($ticker, $livePrice, $series);
            }
            if (in_array($ticker, self::SELF_RADAR_TICKERS, true)) {
                $selfRadar[] = $this->buildSelfRadarRow($ticker, $livePrice, $combined);
            }
        }

        // Tiap seksi diurutkan sendiri (closest-first) -- TIDAK dibandingkan lintas strategi
        // (unit beda: persentase-poin ret_2d/dd_20d vs poin RSI vs persentase harga bottom-rebound
        // tidak apple-to-apple kalau dipaksa satu urutan gabungan).
        usort($gabungan, fn ($a, $b) => ($b['triggered'] <=> $a['triggered']) ?: ($a['distance_pp'] <=> $b['distance_pp']));
        usort($momentum, fn ($a, $b) => ($b['triggered'] <=> $a['triggered']) ?: ($a['distance_pp'] <=> $b['distance_pp']));
        usort($bottomRebound, fn ($a, $b) => ($b['triggered_today'] <=> $a['triggered_today']) ?: ($a['distance_pct'] <=> $b['distance_pct']));
        usort($selfRadar, fn ($a, $b) => ($b['triggered'] <=> $a['triggered']) ?: ($b['score'] <=> $a['score']));

        $selfRadarTop5 = array_values(array_slice(array_values(array_filter($selfRadar, fn ($row) => $row['triggered'])), 0, 5));
        $this->logSelfRadarTop5($selfRadarTop5);

        return [
            'gabungan' => array_values($gabungan),
            'momentum' => array_values($momentum),
            'bottom_rebound' => array_values($bottomRebound),
            'self_radar' => array_values(array_slice($selfRadar, 0, 10)),
            'self_radar_top5' => $selfRadarTop5,
            'generated_at' => now()->timezone('Asia/Jakarta')->format('Y-m-d H:i:s'),
        ];
    }

    private function logSelfRadarTop5(array $rows): void
    {
        if ($rows === []) {
            return;
        }

        try {
            $now = now()->timezone('Asia/Jakarta');
            $signalDate = $now->toDateString();
            $entryStart = $now->copy()->setTime(15, 40);
            $entryEnd = $now->copy()->setTime(15, 45);
            $trailingStart = $now->copy()->addWeekday()->setTime(9, 30);

            foreach ($rows as $rank => $row) {
                $existing = SelfRadarSignalLog::query()
                    ->where('ticker', $row['ticker'])
                    ->whereDate('signal_date', $signalDate)
                    ->first();

                SelfRadarSignalLog::query()->updateOrCreate(
                    ['ticker' => $row['ticker'], 'signal_date' => $signalDate],
                    [
                        'rank' => $rank + 1,
                        'price_at_first_seen' => $existing?->price_at_first_seen ?? $row['price_now'],
                        'latest_price' => $row['price_now'],
                        'rsi14' => $row['rsi14_now'],
                        'ret_5d_pct' => $row['ret_5d_pct'],
                        'dd_20d_pct' => $row['dd_20d_pct'],
                        'score' => $row['score'],
                        'first_seen_at' => $existing?->first_seen_at ?? $now,
                        'last_seen_at' => $now,
                        'entry_window_start_at' => $entryStart,
                        'entry_window_end_at' => $entryEnd,
                        'trailing_start_at' => $trailingStart,
                    ]
                );
            }
        } catch (Throwable) {
            return;
        }
    }

    private function buildSelfRadarRow(string $ticker, float $livePrice, array $combined): array
    {
        $scanDate = now()->timezone('Asia/Jakarta');
        $trailingStartDate = $scanDate->copy()->addWeekday();
        $rsiNow = $this->rsiWilder($combined, 14);
        $ret5d = $this->pctChange($combined, 5);
        $dd20 = $this->drawdown20($combined);
        $triggered = $rsiNow !== null && $ret5d !== null && $dd20 !== null
            && $rsiNow >= self::SELF_RADAR_RSI_MIN
            && $ret5d >= self::SELF_RADAR_RET_5D_MIN
            && $dd20 >= self::SELF_RADAR_DD_20D_MIN;

        return [
            'ticker' => $ticker,
            'strategy' => 'SELF_RADAR_V1',
            'price_now' => round($livePrice, 2),
            'rsi14_now' => $rsiNow !== null ? round($rsiNow, 2) : null,
            'ret_5d_pct' => $ret5d !== null ? round($ret5d * 100, 2) : null,
            'dd_20d_pct' => $dd20 !== null ? round($dd20 * 100, 2) : null,
            'triggered' => $triggered,
            'score' => round(($ret5d ?? -9) * 100 + (($rsiNow ?? 0) - 60) / 10 + (($dd20 ?? -9) * 10), 2),
            'scan_date' => $scanDate->toDateString(),
            'entry_date' => $scanDate->toDateString(),
            'trailing_start_at' => $trailingStartDate->format('Y-m-d 09:30'),
            'entry_plan' => sprintf(
                'Sinyal masuk %s; entry %s dekat close; trailing stop 1%% aktif %s WIB',
                $scanDate->toDateString(),
                $scanDate->toDateString(),
                $trailingStartDate->format('Y-m-d 09:30'),
            ),
            'status' => $triggered ? 'BUY SORE INI (EXPERIMENTAL)' : 'WAIT',
        ];
    }

    private function buildGabunganRow(string $ticker, float $livePrice, array $combined): array
    {
        $ret2d = $this->pctChange2($combined);
        $dd20 = $this->drawdown20($combined);

        $distRet2d = $ret2d !== null ? ($ret2d - self::DROP_THRESHOLD) * 100 : null; // percentage points
        $distDd20 = null;
        if (in_array($ticker, self::DRAWDOWN_LEG_TICKERS, true) && $dd20 !== null) {
            $distDd20 = ($dd20 - self::DRAWDOWN_THRESHOLD) * 100;
        }

        $legs = array_filter([$distRet2d, $distDd20], fn ($v) => $v !== null);
        $primaryDistance = count($legs) > 0 ? min($legs) : 999.0;
        $triggered = $primaryDistance <= 0;

        return [
            'ticker' => $ticker,
            'strategy' => 'GABUNGAN',
            'price_now' => round($livePrice, 2),
            'ret_2d_pct' => $ret2d !== null ? round($ret2d * 100, 2) : null,
            'ret_2d_threshold_pct' => self::DROP_THRESHOLD * 100,
            'ret_2d_distance_pp' => $distRet2d !== null ? round($distRet2d, 2) : null,
            'dd_20d_pct' => $dd20 !== null ? round($dd20 * 100, 2) : null,
            'dd_20d_threshold_pct' => $distDd20 !== null ? self::DRAWDOWN_THRESHOLD * 100 : null,
            'dd_20d_distance_pp' => $distDd20 !== null ? round($distDd20, 2) : null,
            'distance_pp' => round($primaryDistance, 2),
            'triggered' => $triggered,
        ];
    }

    private function buildMomentumRow(string $ticker, float $livePrice, array $combined): array
    {
        $rsiNow = $this->rsiWilder($combined, 14);
        $distance = $rsiNow !== null ? (self::MOMENTUM_RSI_THRESHOLD - $rsiNow) : null;
        $triggered = $distance !== null && $distance < 0;

        return [
            'ticker' => $ticker,
            'strategy' => 'MOMENTUM',
            'price_now' => round($livePrice, 2),
            'rsi14_now' => $rsiNow !== null ? round($rsiNow, 2) : null,
            'rsi_threshold' => self::MOMENTUM_RSI_THRESHOLD,
            'distance_pp' => $distance !== null ? round($distance, 2) : 999.0,
            'triggered' => $triggered,
        ];
    }

    private function buildBottomReboundRow(string $ticker, float $livePrice, array $series): array
    {
        // bottom_10d PAKAI DATA KEMARIN SAJA (bukan termasuk hari ini) -- sama persis
        // detect_bottom_rebound() python: threshold dihitung dari prev_row["bottom_10d"].
        $last10 = array_slice($series, -10);
        $bottomPrev = count($last10) === 10 ? min($last10) : null;
        $thresholdPrice = $bottomPrev !== null ? $bottomPrev * (1 + self::BOTTOM_REBOUND_THRESHOLD) : null;

        $closeYesterday = end($series);
        $wasAboveYesterday = $thresholdPrice !== null && $closeYesterday >= $thresholdPrice;
        $isAboveNow = $thresholdPrice !== null && $livePrice >= $thresholdPrice;

        // "Cross baru" = kemarin BELUM di atas ambang, sekarang (estimasi) SUDAH -- ini yang match
        // definisi "cross pertama" di detect_bottom_rebound() python. Kalau kemarin SUDAH di atas
        // ambang, harga bertahan tinggi hari ini BUKAN sinyal baru (crossing-nya sudah terjadi di
        // hari sebelumnya, entah sudah ke-log entah terlewat).
        $triggeredToday = $isAboveNow && ! $wasAboveYesterday;

        $distancePct = $thresholdPrice !== null && $thresholdPrice > 0
            ? ($livePrice - $thresholdPrice) / $thresholdPrice * 100
            : null;

        return [
            'ticker' => $ticker,
            'strategy' => 'BOTTOM_REBOUND',
            'price_now' => round($livePrice, 2),
            'bottom_10d_prev' => $bottomPrev !== null ? round($bottomPrev, 2) : null,
            'threshold_price' => $thresholdPrice !== null ? round($thresholdPrice, 2) : null,
            'distance_pct' => $distancePct !== null ? round($distancePct, 2) : 999.0,
            'already_in_zone' => $wasAboveYesterday,
            'triggered_today' => $triggeredToday,
        ];
    }

    /**
     * RSI Wilder/EWM rekursif -- SAMA PERSIS formula pandas `.ewm(alpha=1/period, adjust=False)`
     * di detect_signal.py::rsi(). BEDA dari FeatureBuilderService::rsi() (simple average) --
     * WAJIB pakai versi ini di sini supaya "jarak ke threshold" konsisten dgn sinyal resmi.
     * Butuh buffer panjang (>=150 hari) utk konvergen -- lihat komentar Fase BY di
     * detect_signal.py soal window-sensitivity kalau buffer terlalu pendek.
     */
    private function rsiWilder(array $closes, int $period = 14): ?float
    {
        $n = count($closes);
        if ($n < $period + 2) {
            return null;
        }

        $alpha = 1 / $period;
        $avgGain = null;
        $avgLoss = null;

        for ($i = 1; $i < $n; $i++) {
            $delta = $closes[$i] - $closes[$i - 1];
            $gain = max($delta, 0.0);
            $loss = max(-$delta, 0.0);

            if ($avgGain === null) {
                // Seed EWM dari delta PERTAMA -- sama persis perilaku pandas ewm(adjust=False)
                // saat baris pertama (hasil diff() yg NaN) dilewati otomatis.
                $avgGain = $gain;
                $avgLoss = $loss;

                continue;
            }

            $avgGain = (1 - $alpha) * $avgGain + $alpha * $gain;
            $avgLoss = (1 - $alpha) * $avgLoss + $alpha * $loss;
        }

        if ($avgLoss === null) {
            return null;
        }
        if ($avgLoss == 0.0) {
            return 100.0; // tidak pernah rugi sepanjang window -- RS -> infinity, RSI -> 100
        }

        $rs = $avgGain / $avgLoss;

        return 100 - (100 / (1 + $rs));
    }

    /** pandas pct_change(2): (close[i] - close[i-2]) / close[i-2], dihitung di baris TERAKHIR. */
    private function pctChange2(array $closes): ?float
    {
        $n = count($closes);
        if ($n < 3) {
            return null;
        }
        $prev2 = $closes[$n - 3];
        if ($prev2 == 0.0) {
            return null;
        }

        return ($closes[$n - 1] - $prev2) / $prev2;
    }

    private function pctChange(array $closes, int $period): ?float
    {
        $n = count($closes);
        if ($n <= $period) {
            return null;
        }
        $prev = $closes[$n - 1 - $period];
        if ($prev == 0.0) {
            return null;
        }

        return ($closes[$n - 1] - $prev) / $prev;
    }

    /** dd_20d = close / rolling(20).max() - 1, dihitung di baris TERAKHIR. */
    private function drawdown20(array $closes): ?float
    {
        $n = count($closes);
        if ($n < 20) {
            return null;
        }
        $window = array_slice($closes, -20);
        $max = max($window);
        if ($max == 0.0) {
            return null;
        }

        return end($closes) / $max - 1;
    }

    private function livePrice(Stock $stock): ?float
    {
        $ttl = (int) config('market.refresh_seconds', 60);

        try {
            // Cache key SAMA PERSIS dgn TradeController::livePnlFor() -- sengaja, supaya kalau
            // /trades/live dan /trades/radar dibuka bersamaan, keduanya berbagi 1 quote yg sama
            // (bukan 2 request terpisah ke provider utk ticker yg sama).
            $quote = Cache::remember(
                "trade-live-quote:{$stock->code}",
                $ttl,
                fn () => $this->liveMarketData->quote($stock)
            );
        } catch (Throwable $e) {
            return null;
        }

        $last = $quote['last'] ?? null;

        return $last !== null ? (float) $last : null;
    }

    /**
     * Historical daily close via endpoint publik Yahoo Finance yang sama dgn HttpMarketDataProvider
     * (pola sama persis TradeController::fetchIhsgSeries()). Cache 15 menit -- ini request
     * eksternal, jangan tembak tiap kali halaman radar di-poll (poll interval 45 detik jauh lebih
     * sering dari TTL cache kalau tidak di-cache).
     *
     * Hari INI SELALU di-exclude eksplisit dari hasil (walau Yahoo chart API kadang menyertakan
     * bar intraday parsial untuk hari berjalan) -- radar SELALU pakai harga live terpisah
     * (livePrice()) sbg hipotetis closing, supaya tidak dobel-hitung / tidak ambigu sumber harga
     * hari ini yang mana yang dipakai.
     *
     * @return list<float> closes terurut tanggal naik, TIDAK termasuk hari ini
     */
    private function historicalSeries(string $ticker, ?Stock $stock): array
    {
        $today = now()->timezone('Asia/Jakarta')->format('Y-m-d');

        $series = Cache::store('file')->remember("trades:radar-series:{$ticker}:v1", now()->addMinutes(15), function () use ($ticker, $today) {
            try {
                $resp = Http::withHeaders(['User-Agent' => 'Mozilla/5.0'])
                    ->timeout(15)
                    ->get("https://query2.finance.yahoo.com/v8/finance/chart/{$ticker}.JK", [
                        'range' => '2y',
                        'interval' => '1d',
                    ]);

                if (! $resp->ok()) {
                    return [];
                }

                $result = $resp->json('chart.result.0');
                if (! $result) {
                    return [];
                }

                $timestamps = $result['timestamp'] ?? [];
                $closes = $result['indicators']['quote'][0]['close'] ?? [];

                $series = [];
                foreach ($timestamps as $i => $ts) {
                    $close = $closes[$i] ?? null;
                    if ($close === null) {
                        continue;
                    }
                    $date = Carbon::createFromTimestamp($ts)->timezone('Asia/Jakarta')->format('Y-m-d');
                    if ($date === $today) {
                        continue; // exclude hari ini -- lihat docblock method
                    }
                    $series[] = (float) $close;
                }

                return $series;
            } catch (Throwable $e) {
                return [];
            }
        });

        if (count($series) >= 25 || ! $stock) {
            return $series;
        }

        return $this->databaseHistoricalSeries($stock, $today);
    }

    /** @return list<float> */
    private function databaseHistoricalSeries(Stock $stock, string $today): array
    {
        $rows = StockPrice::query()
            ->where('stock_id', $stock->id)
            ->whereDate('price_date', '<', $today)
            ->whereNotNull('close')
            ->orderByDesc('price_date')
            ->limit(260)
            ->get()
            ->sortBy('price_date')
            ->values();

        return StockPrice::canonicalize($rows)
            ->pluck('close')
            ->map(fn ($close) => (float) $close)
            ->values()
            ->all();
    }
}
