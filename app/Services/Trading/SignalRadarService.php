<?php

namespace App\Services\Trading;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\SelfRadarSignalLog;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\News\NewsEventClassifierService;
use Carbon\Carbon;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;
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
    // Fase EY: TINS dipindahkan ke strategi khusus BOTTOM-TO-TOP SWING karena strategi GABUNGAN
    // kaku terbukti rugi (-11.75%) di TINS, sedangkan Bottom-to-Top untung besar (+84.66%).
    private const GABUNGAN_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'PTRO', 'ENRG', 'RAJA', 'INET'];

    private const MOMENTUM_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'DSSA'];

    private const BOTTOM_REBOUND_TICKERS = ['BUMI', 'DEWA'];

    private const SELF_RADAR_TICKERS = ['BAJA', 'MCAS', 'GDST', 'MDIA', 'BYAN', 'PACK', 'KOTA', 'MGLV', 'SLIS', 'FAST', 'TEBE', 'IATA', 'JGLE', 'KIJA', 'SINI', 'GULA', 'JKON', 'JARR', 'INET', 'NSSS', 'DEWA', 'ISAT', 'CUAN', 'PADA', 'WIFI', 'SSIA', 'HATM', 'ESSA', 'BRMS', 'FPNI'];

    // Ticker yg leg drawdown_20d berlaku -- SAMA PERSIS COMBINED_RULE_TICKERS python (8 ticker,
    // SMGR sengaja TIDAK termasuk -- gagal gate P4 validasi ketat, tetap ret_2d saja).
    private const DRAWDOWN_LEG_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'ESSA', 'UNVR', 'PTRO', 'ENRG', 'RAJA'];

    private const DROP_THRESHOLD = -0.05;       // ret_2d, sama persis DROP_THRESHOLD python

    private const DRAWDOWN_THRESHOLD = -0.20;   // dd_20d, sama persis DRAWDOWN_THRESHOLD python

    private const MOMENTUM_RSI_THRESHOLD = 60.0; // sama persis MOMENTUM_RSI_THRESHOLD python

    private const BOTTOM_REBOUND_THRESHOLD = 0.05; // sama persis BOTTOM_REBOUND_THRESHOLD python

    private const SELF_RADAR_RSI_MIN = 60.0;

    private const SELF_RADAR_RET_5D_MIN = 0.05;

    private const SELF_RADAR_DD_20D_MIN = -0.05;

    private TradeQualityGraderService $qualityGrader;

    private NewsEventClassifierService $newsClassifier;

    public function __construct(
        private LiveMarketDataService $liveMarketData,
        ?TradeQualityGraderService $qualityGrader = null,
        ?NewsEventClassifierService $newsClassifier = null
    ) {
        $this->qualityGrader = $qualityGrader ?? app(TradeQualityGraderService::class);
        $this->newsClassifier = $newsClassifier ?? app(NewsEventClassifierService::class);
    }

    /**
     * @return array{gabungan: array, momentum: array, bottom_rebound: array, self_radar: array, generated_at: string}
     */
    public function build(): array
    {
        $allTickers = collect(self::GABUNGAN_TICKERS)
            ->merge(self::MOMENTUM_TICKERS)
            ->merge(self::BOTTOM_REBOUND_TICKERS)
            ->merge(self::SELF_RADAR_TICKERS)
            ->merge(['TINS'])
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
                $gabungan[] = $this->buildGabunganRow($ticker, $livePrice, $combined, $stock);
            }
            if (in_array($ticker, self::MOMENTUM_TICKERS, true)) {
                $momentum[] = $this->buildMomentumRow($ticker, $livePrice, $combined, $stock);
            }
            if (in_array($ticker, self::BOTTOM_REBOUND_TICKERS, true)) {
                $bottomRebound[] = $this->buildBottomReboundRow($ticker, $livePrice, $series, $stock);
            }
            if (in_array($ticker, self::SELF_RADAR_TICKERS, true)) {
                $selfRadar[] = $this->buildSelfRadarRow($ticker, $livePrice, $combined, $stock);
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

        $tinsStock = $stocks->get('TINS') ?? Stock::where('code', 'TINS')->first();
        $tinsBottomToTop = $this->buildTinsBottomToTopRow($tinsStock);
        $bsjpMomentum = $this->buildBsjpMomentumRows(10);

        // Pilar 1+2+3: Batch-attach filtered News Event badges (CATALYST / HARD_RISK / SUSPENSION / PANIC_DROP)
        $newsTickers = collect($gabungan)->pluck('ticker')
            ->merge(collect($momentum)->pluck('ticker'))
            ->merge(collect($bottomRebound)->pluck('ticker'))
            ->merge(collect($bsjpMomentum['candidates'] ?? [])->pluck('ticker'))
            ->push('TINS')
            ->filter()
            ->unique()
            ->values()
            ->all();

        $newsMap = $this->newsClassifier->summarizeBatch($newsTickers, 14);
        $attachNews = fn (array $rows) => array_map(function (array $row) use ($newsMap) {
            $tk = strtoupper((string) ($row['ticker'] ?? ''));
            $row['news_event'] = $newsMap[$tk] ?? null;

            return $row;
        }, array_values($rows));

        $gabungan = $attachNews($gabungan);
        $momentum = $attachNews($momentum);
        $bottomRebound = $attachNews($bottomRebound);
        if (is_array($tinsBottomToTop) && isset($tinsBottomToTop['ticker'])) {
            $tinsBottomToTop['news_event'] = $newsMap[strtoupper((string) $tinsBottomToTop['ticker'])] ?? null;
        }
        if (isset($bsjpMomentum['candidates']) && is_array($bsjpMomentum['candidates'])) {
            $bsjpMomentum['candidates'] = $attachNews($bsjpMomentum['candidates']);
        }

        return [
            'market_regime' => $this->buildMarketRegimeBanner(),
            'gabungan' => $gabungan,
            'momentum' => $momentum,
            'bottom_rebound' => $bottomRebound,
            'self_radar' => array_values(array_slice($selfRadar, 0, 10)),
            'self_radar_top5' => $selfRadarTop5,
            'tins_bottom_to_top' => $tinsBottomToTop,
            'bsjp_momentum' => $bsjpMomentum,
            'generated_at' => now()->timezone('Asia/Jakarta')->format('Y-m-d H:i:s'),
        ];
    }

    /**
     * Build live IHSG Market Regime & Red-Streak Banner aligned with GEMINI.md Protocol #1.
     *
     * @return array<string, mixed>
     */
    public function buildMarketRegimeBanner(): array
    {
        $cacheStore = app()->environment('testing') ? 'array' : 'file';

        return Cache::store($cacheStore)->remember('trades:radar-ihsg-regime:v1', now()->addMinutes(15), function () {
            $closes = [];
            try {
                $resp = Http::withHeaders(['User-Agent' => 'Mozilla/5.0'])
                    ->timeout(10)
                    ->get('https://query2.finance.yahoo.com/v8/finance/chart/%5EJKSE', [
                        'range' => '3mo',
                        'interval' => '1d',
                    ]);

                if ($resp->ok()) {
                    $result = $resp->json('chart.result.0');
                    $rawCloses = $result['indicators']['quote'][0]['close'] ?? [];
                    foreach ($rawCloses as $c) {
                        if ($c !== null && (float) $c > 0) {
                            $closes[] = (float) $c;
                        }
                    }
                }
            } catch (Throwable $e) {
                $closes = [];
            }

            if (count($closes) < 2) {
                return [
                    'available' => false,
                    'status' => 'UNKNOWN',
                    'label' => 'Data IHSG Belum Tersedia',
                    'advice' => 'Pastikan koneksi data pasar aktif untuk validasi rezim IHSG.',
                ];
            }

            $latest = $closes[count($closes) - 1];
            $prev = $closes[count($closes) - 2];
            $chg1d = $prev > 0 ? round((($latest - $prev) / $prev) * 100, 2) : 0.0;
            $ma20Slice = array_slice($closes, -min(20, count($closes)));
            $ma20 = round(array_sum($ma20Slice) / count($ma20Slice), 2);
            $vsMa20 = $ma20 > 0 ? round((($latest - $ma20) / $ma20) * 100, 2) : 0.0;

            $redStreak = 0;
            $greenStreak = 0;
            for ($i = count($closes) - 1; $i >= 1; $i--) {
                if ($closes[$i] < $closes[$i - 1]) {
                    if ($greenStreak > 0) {
                        break;
                    }
                    $redStreak++;
                } elseif ($closes[$i] > $closes[$i - 1]) {
                    if ($redStreak > 0) {
                        break;
                    }
                    $greenStreak++;
                } else {
                    break;
                }
            }

            $isCrashGuard = $chg1d <= -1.0 || ($latest < $ma20 && $redStreak >= 3);
            $isBelowMa20 = $latest < $ma20;

            if ($isCrashGuard) {
                $status = 'CASH_IS_KING';
                $label = '⛔ CASH IS KING / DEFENSIF';
                $advice = 'IHSG sedang koreksi tajam / di bawah MA20 dengan streak merah. DILARANG all-in Drawdown Bounce Hari-1; tunggu konfirmasi candle hijau atau Day-2 Morning Flush.';
            } elseif ($isBelowMa20) {
                $status = 'DEFENSIVE';
                $label = '⚠️ DEFENSIF / SELEKTIF';
                $advice = 'IHSG di bawah MA20. Batasi alokasi 25–30% kas hanya pada sinyal Grade A+/A dengan Lower Wick >= 1,0% & tanpa Hard Risk berita.';
            } else {
                $status = 'BULLISH';
                $label = '🟢 REZIM AMAN (DI ATAS MA20)';
                $advice = 'IHSG berdiri di atas MA20. Eksekusi penuh sesuai Grade A+/A & disiplin 3-Lapis Proteksi.';
            }

            return [
                'available' => true,
                'close' => round($latest, 2),
                'change_1d_pct' => $chg1d,
                'ma20' => $ma20,
                'vs_ma20_pct' => $vsMa20,
                'red_streak' => $redStreak,
                'green_streak' => $greenStreak,
                'status' => $status,
                'label' => $label,
                'advice' => $advice,
            ];
        });
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

    private function buildSelfRadarRow(string $ticker, float $livePrice, array $combined, ?Stock $stock = null): array
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

        $candle = $this->extractRecentCandleFeatures($stock, $livePrice);
        $gradeResult = $this->qualityGrader->gradeTrade(
            $ticker,
            'momentum',
            array_merge($candle, [
                'sub_signal' => 'momentum',
                'rsi_14' => $rsiNow,
            ])
        );

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
            'quality' => [
                'grade' => $gradeResult['grade'],
                'score' => $gradeResult['quality_score'],
                'status' => $gradeResult['dss_status'],
                'recommended_sizing_pct' => $gradeResult['recommended_sizing_pct'],
                'action_advice' => $triggered
                    ? '⚡ Overnight Continuation: Masuk Pukul 15:40 - 15:45 WIB'
                    : '⏳ Menunggu Kriteria RSI & Ret5d Terpenuhi',
                'ticker_tier' => $gradeResult['snapshot']['ticker_tier'] ?? 'TIER_B',
                'vol_ratio' => $gradeResult['snapshot']['vol_ratio_ma20'] ?? null,
                'lower_wick' => $gradeResult['snapshot']['lower_wick_pct'] ?? null,
                'rsi_14' => $rsiNow !== null ? round($rsiNow, 1) : null,
                'sub_signal' => 'momentum',
            ],
        ];
    }

    private function extractRecentCandleFeatures(?Stock $stock, float $livePrice): array
    {
        if (! $stock) {
            return ['lower_wick_pct' => null, 'vol_ratio_ma20' => null];
        }

        try {
            $recent = StockPrice::where('stock_id', $stock->id)
                ->orderByDesc('price_date')
                ->take(21)
                ->get();

            if ($recent->isEmpty()) {
                return ['lower_wick_pct' => null, 'vol_ratio_ma20' => null];
            }

            $latest = $recent->first();
            $prev20 = $recent->slice(1, 20);
            $avgVol = $prev20->avg('volume');

            $volRatio = ($avgVol && $avgVol > 0 && $latest->volume > 0)
                ? round((float) $latest->volume / (float) $avgVol, 2)
                : null;

            $low = (float) $latest->low;
            $close = $livePrice > 0 ? $livePrice : (float) $latest->close;
            $lowerWick = ($low > 0 && $close >= $low)
                ? round(($close - $low) / $low * 100, 2)
                : null;

            return [
                'lower_wick_pct' => $lowerWick,
                'vol_ratio_ma20' => $volRatio,
            ];
        } catch (Throwable) {
            return ['lower_wick_pct' => null, 'vol_ratio_ma20' => null];
        }
    }

    private function buildGabunganRow(string $ticker, float $livePrice, array $combined, ?Stock $stock = null): array
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

        $rsiNow = $this->rsiWilder($combined, 14);
        $candle = $this->extractRecentCandleFeatures($stock, $livePrice);
        $subSignal = ($distDd20 !== null && $distDd20 <= 0 && $distRet2d !== null && $distRet2d <= 0)
            ? 'ganda'
            : (($distDd20 !== null && $distDd20 <= 0) ? 'drawdown' : 'ret2d');

        $gradeResult = $this->qualityGrader->gradeTrade(
            $ticker,
            'gabungan',
            array_merge($candle, [
                'sub_signal' => $subSignal,
                'rsi_14' => $rsiNow,
                'ret_2d' => $ret2d !== null ? $ret2d * 100 : null,
                'dd_20d' => $dd20 !== null ? $dd20 * 100 : null,
            ])
        );

        $actionAdvice = match ($gradeResult['grade']) {
            'A+' => '🚀 Setup Sempurna (WR 72.6%): Beli Penuh 100% Pre-Closing (15:50 WIB)',
            'A' => '✅ Setup Kuat (WR 59.7%): Beli Standar 100% Pre-Closing (15:50 WIB)',
            'B' => '⚠️ Setup Moderat: Alokasi Dibatasi 50% / Tunggu Lonjakan Volume',
            default => '⛔ Rawan False Bounce (Dead Low): DILARANG Beli Hari-1! Tunggu Day-2 Morning Flush',
        };

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
            'quality' => [
                'grade' => $gradeResult['grade'],
                'score' => $gradeResult['quality_score'],
                'status' => $gradeResult['dss_status'],
                'recommended_sizing_pct' => $gradeResult['recommended_sizing_pct'],
                'action_advice' => $actionAdvice,
                'ticker_tier' => $gradeResult['snapshot']['ticker_tier'] ?? 'TIER_B',
                'vol_ratio' => $gradeResult['snapshot']['vol_ratio_ma20'] ?? null,
                'lower_wick' => $gradeResult['snapshot']['lower_wick_pct'] ?? null,
                'rsi_14' => $rsiNow !== null ? round($rsiNow, 1) : null,
                'sub_signal' => $subSignal,
            ],
        ];
    }

    private function buildMomentumRow(string $ticker, float $livePrice, array $combined, ?Stock $stock = null): array
    {
        $rsiNow = $this->rsiWilder($combined, 14);
        $distance = $rsiNow !== null ? (self::MOMENTUM_RSI_THRESHOLD - $rsiNow) : null;
        $triggered = $distance !== null && $distance < 0;

        $candle = $this->extractRecentCandleFeatures($stock, $livePrice);
        $gradeResult = $this->qualityGrader->gradeTrade(
            $ticker,
            'momentum',
            array_merge($candle, [
                'sub_signal' => 'momentum',
                'rsi_14' => $rsiNow,
            ])
        );

        $actionAdvice = match ($gradeResult['grade']) {
            'A+' => '🚀 Momentum Sempurna: Beli Penuh 100% Pre-Closing',
            'A' => '✅ Momentum Kuat: Beli Standar 100%',
            'B' => '⚠️ Momentum Moderat: Porsi 50%',
            default => '⛔ Evaluasi Volatilitas / Tunggu Konfirmasi',
        };

        return [
            'ticker' => $ticker,
            'strategy' => 'MOMENTUM',
            'price_now' => round($livePrice, 2),
            'rsi14_now' => $rsiNow !== null ? round($rsiNow, 2) : null,
            'rsi_threshold' => self::MOMENTUM_RSI_THRESHOLD,
            'distance_pp' => $distance !== null ? round($distance, 2) : 999.0,
            'triggered' => $triggered,
            'quality' => [
                'grade' => $gradeResult['grade'],
                'score' => $gradeResult['quality_score'],
                'status' => $gradeResult['dss_status'],
                'recommended_sizing_pct' => $gradeResult['recommended_sizing_pct'],
                'action_advice' => $actionAdvice,
                'ticker_tier' => $gradeResult['snapshot']['ticker_tier'] ?? 'TIER_B',
                'vol_ratio' => $gradeResult['snapshot']['vol_ratio_ma20'] ?? null,
                'lower_wick' => $gradeResult['snapshot']['lower_wick_pct'] ?? null,
                'rsi_14' => $rsiNow !== null ? round($rsiNow, 1) : null,
                'sub_signal' => 'momentum',
            ],
        ];
    }

    private function buildBottomReboundRow(string $ticker, float $livePrice, array $series, ?Stock $stock = null): array
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

        $rsiNow = $this->rsiWilder(array_merge($series, [$livePrice]), 14);
        $candle = $this->extractRecentCandleFeatures($stock, $livePrice);
        $gradeResult = $this->qualityGrader->gradeTrade(
            $ticker,
            'bottom_rebound',
            array_merge($candle, [
                'sub_signal' => 'bottom_rebound',
                'rsi_14' => $rsiNow,
            ])
        );

        return [
            'ticker' => $ticker,
            'strategy' => 'BOTTOM_REBOUND',
            'price_now' => round($livePrice, 2),
            'bottom_10d_prev' => $bottomPrev !== null ? round($bottomPrev, 2) : null,
            'threshold_price' => $thresholdPrice !== null ? round($thresholdPrice, 2) : null,
            'distance_pct' => $distancePct !== null ? round($distancePct, 2) : 999.0,
            'already_in_zone' => $wasAboveYesterday,
            'triggered_today' => $triggeredToday,
            'quality' => [
                'grade' => $gradeResult['grade'],
                'score' => $gradeResult['quality_score'],
                'status' => $gradeResult['dss_status'],
                'recommended_sizing_pct' => $gradeResult['recommended_sizing_pct'],
                'action_advice' => $triggeredToday
                    ? '🎯 Cross Baru Hari Ini: Beli Dekat Closing Sesi 2'
                    : '⏸️ Belum Memenuhi Syarat Rebound Baru',
                'ticker_tier' => $gradeResult['snapshot']['ticker_tier'] ?? 'TIER_B',
                'vol_ratio' => $gradeResult['snapshot']['vol_ratio_ma20'] ?? null,
                'lower_wick' => $gradeResult['snapshot']['lower_wick_pct'] ?? null,
                'rsi_14' => $rsiNow !== null ? round($rsiNow, 1) : null,
                'sub_signal' => 'bottom_rebound',
            ],
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
        $cacheStore = app()->environment('testing') ? 'array' : 'file';
        $series = Cache::store($cacheStore)->remember("trades:radar-series:{$ticker}:v1", now()->addMinutes(15), function () use ($ticker, $today) {
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

    /**
     * Fase EY: Estimasi Live Radar TINS Bottom-to-Top Swing (Ambil di Dasar, Jual di Pucuk).
     */
    private function buildTinsBottomToTopRow(?Stock $stock): ?array
    {
        if (! $stock) {
            return null;
        }

        $series = $this->historicalSeries('TINS', $stock);
        if (count($series) < 25) {
            return null;
        }

        $quote = $this->liveMarketData->quote($stock);
        $livePrice = $quote['last'] ?? end($series);
        if (! $livePrice) {
            return null;
        }

        $livePrice = (float) $livePrice;
        $combined = array_merge($series, [$livePrice]);
        $rsiNow = $this->rsiWilder($combined, 14);

        // Stochastic %K (14 period)
        $today = now()->timezone('Asia/Jakarta')->toDateString();
        $historyPrices = StockPrice::query()
            ->where('stock_id', $stock->id)
            ->whereDate('price_date', '<', $today)
            ->orderByDesc('price_date')
            ->limit(25)
            ->get();

        $highs = $historyPrices->take(13)->pluck('high')->map(fn ($v) => (float) $v)->all();
        $lows = $historyPrices->take(13)->pluck('low')->map(fn ($v) => (float) $v)->all();

        $todayHigh = (float) ($quote['high'] ?? $livePrice);
        $todayLow = (float) ($quote['low'] ?? $livePrice);
        $todayOpen = (float) ($quote['open'] ?? end($series));
        $closeYesterday = (float) end($series);

        $highs[] = $todayHigh;
        $lows[] = $todayLow;

        $maxHigh14 = count($highs) > 0 ? max($highs) : $livePrice;
        $minLow14 = count($lows) > 0 ? min($lows) : $livePrice;

        $stochK = ($maxHigh14 > $minLow14)
            ? (($livePrice - $minLow14) / ($maxHigh14 - $minLow14)) * 100
            : 50.0;

        // Bollinger Band %B (20 period)
        $last20 = array_slice($combined, -20);
        $count20 = count($last20);
        $mean20 = array_sum($last20) / $count20;
        $variance = 0.0;
        foreach ($last20 as $val) {
            $variance += pow($val - $mean20, 2);
        }
        $std20 = sqrt($variance / $count20);
        $bbLower = $mean20 - 2 * $std20;
        $bbUpper = $mean20 + 2 * $std20;
        $bbPctB = ($bbUpper > $bbLower)
            ? ($livePrice - $bbLower) / ($bbUpper - $bbLower)
            : 0.5;

        $isGreen = ($livePrice > $todayOpen) && ($livePrice > $closeYesterday);
        $condDip = ($stochK < 30) || ($bbPctB < 0.25) || ($rsiNow !== null && $rsiNow < 45);
        $triggered = $condDip && $isGreen;

        if ($triggered) {
            $status = 'BUY SEKARANG (BOTTOM REBOUND)';
        } elseif ($condDip && ! $isGreen) {
            $status = 'DISKON SIKLUS (TUNGGU LILIN HIJAU)';
        } elseif ($stochK > 75 || $bbPctB > 0.85 || ($rsiNow !== null && $rsiNow > 65)) {
            $status = 'OVERBOUGHT (AREA PUCUK - JANGAN FOMO)';
        } else {
            $status = 'WAIT (MENUNGGU SIKLUS DISKON)';
        }

        $slPrice = round($livePrice * 0.97, 0);

        $gradeResult = $this->qualityGrader->gradeTrade(
            'TINS',
            'bottom_to_top',
            [
                'rsi_14' => $rsiNow,
                'sub_signal' => 'bottom_to_top',
            ]
        );

        return [
            'ticker' => 'TINS',
            'strategy' => 'BOTTOM_TO_TOP',
            'price_now' => round($livePrice, 2),
            'open_today' => round($todayOpen, 2),
            'close_yesterday' => round($closeYesterday, 2),
            'is_green' => $isGreen,
            'stoch_k' => round($stochK, 1),
            'bb_pct_b' => round($bbPctB, 2),
            'rsi14' => $rsiNow !== null ? round($rsiNow, 1) : null,
            'sl_price' => $slPrice,
            'triggered' => $triggered,
            'status' => $status,
            'notes' => 'Validasi Kuantitatif: 12 trade, Win Rate 66.7%, Modal Rp10jt jadi Rp18.46M (+84.66%). Auto Cut Loss 3.0%, Kunci Cuan Trailing 2.5% dari Puncak.',
            'quality' => [
                'grade' => $triggered ? 'A+' : ($condDip ? 'B' : 'C'),
                'score' => $triggered ? 88 : ($condDip ? 65 : 45),
                'status' => $triggered ? 'HIGH_CONVICTION_BUY' : 'WAIT_SIGNAL',
                'recommended_sizing_pct' => $triggered ? 100 : 0,
                'action_advice' => $triggered
                    ? '🚀 Rebound Siklus Terkonfirmasi: Beli Pre-Closing (SL -3%, Trailing 2.5%)'
                    : ($condDip ? '⏳ Diskon Siklus: Tunggu Lilin Hijau di Sesi 2' : '⏸️ Area Netral / Pucuk: Jangan FOMO'),
                'ticker_tier' => 'TIER_S',
                'vol_ratio' => null,
                'lower_wick' => null,
                'rsi_14' => $rsiNow !== null ? round($rsiNow, 1) : null,
                'sub_signal' => 'bottom_to_top',
            ],
        ];
    }

    public function buildBsjpMomentumRows(int $limit = 10): array
    {
        if (! Schema::hasTable('idx_daily_summaries')) {
            return [
                'stage' => 'early',
                'stage_label' => 'Radar Pantau Dini (15:00 WIB)',
                'trade_date' => null,
                'candidates' => [],
            ];
        }

        $nowJakarta = now('Asia/Jakarta');
        $today = $nowJakarta->toDateString();
        $hour = (int) $nowJakarta->format('H');
        $minute = (int) $nowJakarta->format('i');

        // Jika hari kerja bursa dan waktu sesi sore (>= 14:50 WIB), otomatis sinkronkan data live jika belum ada
        if (! app()->runningUnitTests() && $nowJakarta->isWeekday() && ($hour >= 15 || ($hour === 14 && $minute >= 50))) {
            $latestCheck = DB::table('idx_daily_summaries')->max('trade_date');
            if ($latestCheck !== $today && ! Cache::has('bsjp_live_sync_throttle')) {
                Cache::put('bsjp_live_sync_throttle', true, now()->addMinutes(10));
                try {
                    Artisan::call('trade:sync-bsjp-live');
                } catch (\Throwable $e) {
                    Log::warning('Auto sync BSJP live error: ' . $e->getMessage());
                }
            }
        }

        $latestDate = DB::table('idx_daily_summaries')->max('trade_date');
        if (! $latestDate) {
            return [
                'stage' => 'early',
                'stage_label' => 'Radar Pantau Dini (15:00 WIB)',
                'trade_date' => null,
                'trade_date_formatted' => null,
                'is_today' => false,
                'last_sync_at' => null,
                'candidates' => [],
            ];
        }

        $priorDate = DB::table('idx_daily_summaries')
            ->where('trade_date', '<', $latestDate)
            ->max('trade_date');

        if (! $priorDate) {
            return [
                'stage' => 'early',
                'stage_label' => 'Radar Pantau Dini (15:00 WIB)',
                'trade_date' => $latestDate,
                'trade_date_formatted' => Carbon::parse($latestDate)->locale('id')->isoFormat('D MMM Y'),
                'is_today' => $latestDate === $today,
                'last_sync_at' => null,
                'candidates' => [],
            ];
        }

        $rows = DB::table('idx_daily_summaries as t')
            ->join('idx_daily_summaries as p', function ($join) use ($priorDate) {
                $join->on('t.stock_code', '=', 'p.stock_code')
                    ->where('p.trade_date', '=', $priorDate);
            })
            ->where('t.trade_date', '=', $latestDate)
            ->where('t.close', '>', DB::raw('t.open'))
            ->where('t.pct_change', '>=', 3.0)
            ->where('t.value', '>=', 100000000)
            ->where('t.volume', '>=', DB::raw('p.volume * 1.5'))
            ->select([
                't.stock_code as ticker',
                't.stock_name as name',
                't.close as price',
                't.open as open_price',
                't.previous as prev_price',
                't.pct_change as return_pct',
                't.volume as volume_today',
                'p.volume as volume_prev',
                DB::raw('t.volume / NULLIF(p.volume, 0) as volume_ratio'),
                't.value as transaction_value',
                't.trade_date',
            ])
            ->orderByDesc('volume_ratio')
            ->orderByDesc('t.value')
            ->take($limit)
            ->get();

        $stage = ($hour < 15 || ($hour === 15 && $minute < 35)) ? 'early' : 'confirm';
        $isToday = $latestDate === $today;
        $lastSyncTime = DB::table('idx_daily_summaries')
            ->where('trade_date', $latestDate)
            ->max('updated_at');

        return [
            'stage' => $stage,
            'stage_label' => $stage === 'early' ? 'Radar Pantau Dini (15:00 WIB)' : 'Konfirmasi Beli (15:35 WIB)',
            'trade_date' => $latestDate,
            'trade_date_formatted' => Carbon::parse($latestDate)->locale('id')->isoFormat('D MMM Y'),
            'is_today' => $isToday,
            'last_sync_at' => $lastSyncTime ? Carbon::parse($lastSyncTime)->timezone('Asia/Jakarta')->format('H:i') . ' WIB' : null,
            'candidates' => $rows->map(function ($r) {
                $price = (float) $r->price;
                $retPct = (float) $r->return_pct;
                $isRocket = $retPct >= 15.0;
                $val = (float) $r->transaction_value;
                $qualityGrade = match (true) {
                    $isRocket => 'B',
                    $val >= 5000000000 => 'A+',
                    default => 'A',
                };
                $qualityScore = match ($qualityGrade) {
                    'A+' => 88,
                    'A' => 74,
                    default => 60,
                };

                return [
                    'ticker' => (string) $r->ticker,
                    'name' => (string) ($r->name ?? $r->ticker),
                    'price' => $price,
                    'open' => (float) $r->open_price,
                    'return_pct' => $retPct,
                    'volume_ratio' => round((float) $r->volume_ratio, 1),
                    'value' => $val,
                    'category' => $isRocket ? 'rocket' : 'sweetspot',
                    'category_label' => $isRocket ? '🚀 Super Rocket' : '🎯 Sweetspot',
                    'category_badge' => $isRocket ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
                    'target_tp' => round($price * 1.025),
                    'stop_loss' => round($price * 0.97),
                    'quality' => [
                        'grade' => $qualityGrade,
                        'score' => $qualityScore,
                        'status' => $qualityGrade === 'A+' ? 'HIGH_CONVICTION_BSJP' : ($qualityGrade === 'A' ? 'STANDARD_BSJP' : 'SELECTIVE_BSJP'),
                        'recommended_sizing_pct' => $qualityGrade === 'B' ? 50 : 100,
                        'action_advice' => $isRocket
                            ? '🚀 Super Rocket: Potensi gap-up tinggi, batasi lot agar terhindar dari guyuran'
                            : '🎯 Sweetspot BSJP: Likuiditas melimpah, antre beli pre-closing 15:50 WIB',
                        'ticker_tier' => 'TIER_A',
                        'vol_ratio' => round((float) $r->volume_ratio, 1),
                        'lower_wick' => null,
                        'rsi_14' => null,
                        'sub_signal' => 'bsjp_momentum',
                    ],
                ];
            })->all(),
        ];
    }
}
