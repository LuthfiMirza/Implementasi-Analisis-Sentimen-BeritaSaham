<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Models\Trade;
use App\Services\MarketData\LiveMarketDataService;
use Carbon\Carbon;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Throwable;

class TradeController extends Controller
{
    /**
     * Fase CN: halaman operasional (posisi terbuka, catat/tutup/hapus manual) -- dipisah dari
     * /trades/laporan supaya tugas harian (buka/tutup posisi) tidak tenggelam di antara stats,
     * episode breakdown, dan tabel riwayat 374+ baris. Preview PnL/WR di sini SELALU GABUNGAN
     * resmi (tidak ada toggle scope) -- detail lengkap + toggle ada di laporan().
     */
    public function index(Request $request)
    {
        $trades = Trade::with('stock')
            ->where('user_id', auth()->id())
            ->orderByDesc('entry_date')
            ->get();

        $closed = $trades->where('status', 'closed');
        $open = $trades->where('status', 'open');

        $officialClosed = $closed->where('strategy_label', 'gabungan');
        $winners = $officialClosed->where('pnl_total', '>', 0);
        $losers = $officialClosed->where('pnl_total', '<=', 0);

        // Fase CO: kartu preview di halaman operasional diganti dari "Trade Closed" (292, angka
        // paling tidak informatif) ke Episode Independen -- lebih jujur menggambarkan performa,
        // sama protokol groupIntoEpisodes() yang dipakai laporan() penuh.
        $episodes = $this->groupIntoEpisodes($officialClosed);
        $episodeWins = collect($episodes)->filter(fn ($ep) => collect($ep)->avg('pnl_total') > 0);

        $preview = [
            'total_pnl' => $officialClosed->sum('pnl_total'),
            'win_rate' => $officialClosed->count() > 0
                ? round($winners->count() / $officialClosed->count() * 100, 1)
                : 0,
            'win' => $winners->count(),
            'loss' => $losers->count(),
            'closed' => $officialClosed->count(),
            'episode_count' => count($episodes),
            'episode_win_rate' => count($episodes) > 0
                ? round($episodeWins->count() / count($episodes) * 100, 1)
                : 0,
        ];

        $stocks = Stock::where('is_active', true)->orderBy('code')->get();
        $live = $this->livePnlFor($open);

        return view('trades.index', compact('trades', 'open', 'stocks', 'live', 'preview'));
    }

    /**
     * Fase CN: halaman laporan lengkap -- stats resmi, toggle GABUNGAN/Semua Strategi (Fase CL),
     * episode independensi per bulan, arsip strategi lain, dan tabel riwayat penuh dengan filter
     * + pagination (Fase CM). Dipisah dari index() supaya operasional harian tetap ringkas.
     */
    public function laporan(Request $request)
    {
        $trades = Trade::with('stock')
            ->where('user_id', auth()->id())
            ->orderByDesc('entry_date')
            ->get();

        $closed = $trades->where('status', 'closed');
        $open = $trades->where('status', 'open');

        // Fase CL: toggle "GABUNGAN (resmi)" vs "Semua Strategi (gabung, ada overlap)" -- user
        // eksplisit minta bisa lihat 2 versi. "all" TIDAK menghapus caveat Fase CA di bawah: kalau
        // scope=all, legacy_ab_ac ikut dijumlah padahal TERBUKTI 100% overlap trigger dengan
        // gabungan (Fase CF) -- jadi profit yang SAMA bisa kehitung dua kali.
        $scope = $request->query('scope') === 'all' ? 'all' : 'gabungan';

        // Fase CA: kartu ringkasan RESMI (default) cuma dihitung dari strategy_label='gabungan'
        // -- 3 aturan drawdown-bounce lama (legacy_stock_only/legacy_ab_ac/GABUNGAN) TERBUKTI
        // tumpang tindih periode untuk saham yang sama (dicek langsung dari notes backfill: "ada
        // tumpang tindih periode dengan catatan lama... user pilih tetap masukkan data baru ini
        // berdampingan"). Menjumlahkan ketiganya dulu (versi sebelum Fase CA) berisiko menghitung
        // untung yang SAMA berkali-kali dengan aturan berbeda. GABUNGAN (Fase BK, aturan yang live
        // SEKARANG) dijadikan acuan resmi default; sisanya tetap tersimpan utuh (TIDAK dihapus)
        // sebagai arsip riset, ditampilkan terpisah lewat $strategyBreakdown di bawah -- KECUALI
        // user pilih scope=all secara eksplisit.
        $officialClosed = $scope === 'all' ? $closed : $closed->where('strategy_label', 'gabungan');
        $officialOpen = $scope === 'all' ? $open : $open->where('strategy_label', 'gabungan');

        // Menang/kalah dari PnL AKTUAL, bukan dari kategori `result` -- exit berbasis waktu
        // (manual_close, mis. aturan drawdown-bounce Fase AB/AC) valid juga dan sebelumnya
        // hilang sama sekali dari Win Rate karena bukan hit_target_1/2 maupun stop_loss.
        $winners = $officialClosed->where('pnl_total', '>', 0);
        $losers = $officialClosed->where('pnl_total', '<=', 0);

        $stats = [
            'total' => $officialOpen->count() + $officialClosed->count(),
            'open' => $officialOpen->count(),
            'closed' => $officialClosed->count(),
            'win' => $winners->count(),
            'loss' => $losers->count(),
            'win_rate' => $officialClosed->count() > 0
                ? round($winners->count() / $officialClosed->count() * 100, 1)
                : 0,
            'total_pnl' => $officialClosed->sum('pnl_total'),
            'avg_rr' => $officialClosed->count() > 0 ? round($officialClosed->avg('actual_rr'), 2) : 0,
            'avg_holding' => $officialClosed->count() > 0 ? round($officialClosed->avg('holding_days'), 1) : 0,
            'best_trade' => $officialClosed->sortByDesc('pnl_total')->first(),
            'worst_trade' => $officialClosed->sortBy('pnl_total')->first(),
            'expectancy' => 0,
        ];

        $avgWin = $winners->avg('pnl_percent') ?? 0;
        $avgLoss = abs($losers->avg('pnl_percent') ?? 0);
        $winRate = $stats['win_rate'] / 100;
        $stats['expectancy'] = round(($winRate * $avgWin) - ((1 - $winRate) * $avgLoss), 2);

        // Episode independence (sama protokol dipakai riset saham baru & averaging-down sesi ini,
        // lihat screen_candidates.py/research_average_down.py) -- trigger yang BERDEKATAN (jeda
        // <=15 hari kalender, per ticker) digabung jadi SATU episode. "111 trade, WR 79.3%" itu
        // MENGGELEMBUNG kalau dibaca sebagai 111 kesempatan independen -- satu koreksi panjang
        // BUMI 2 minggu bisa saja tercatat sebagai 3-4 trade terpisah karena syarat entry kena
        // ulang tiap kali harga jatuh lagi, padahal itu SATU kejadian pasar, bukan tiga.
        $episodes = $this->groupIntoEpisodes($officialClosed);
        $episodeWins = collect($episodes)->filter(fn ($ep) => collect($ep)->avg('pnl_total') > 0);
        $stats['episode_count'] = count($episodes);
        $stats['episode_win_rate'] = count($episodes) > 0
            ? round($episodeWins->count() / count($episodes) * 100, 1)
            : 0;

        // Breakdown per bulan -- dikelompokkan berdasar bulan ENTRY trade PERTAMA di tiap episode
        // (kapan episode itu MULAI), bukan bulan tiap trade mentah -- supaya episode yang
        // membentang lewat batas bulan (mis. trigger 28 Jun, trade lanjutan 3 Jul) tidak
        // terhitung dobel di 2 bulan berbeda.
        $episodesByMonth = collect($episodes)
            ->groupBy(fn ($ep) => collect($ep)->min('entry_date')->format('Y-m'));
        $monthlyBreakdown = $episodesByMonth->map(function ($eps, $month) {
            $epReturns = $eps->map(fn ($ep) => collect($ep)->avg('pnl_total'));
            $wins = $epReturns->filter(fn ($r) => $r > 0)->count();

            return [
                'month' => $month,
                'month_label' => \Carbon\Carbon::createFromFormat('Y-m', $month)->format('M Y'),
                'episode_count' => $eps->count(),
                'trade_count' => $eps->sum(fn ($ep) => count($ep)),
                'win_rate' => $eps->count() > 0 ? round($wins / $eps->count() * 100, 1) : 0,
                'total_pnl' => $eps->sum(fn ($ep) => collect($ep)->sum('pnl_total')),
            ];
        })->sortKeys()->values()->all();

        // Riwayat strategi LAIN (bukan GABUNGAN) -- ditampilkan terpisah, TIDAK ikut kartu resmi
        // di atas, supaya kelihatan tapi tidak tercampur/menggelembungkan angka utama.
        $strategyLabels = [
            'legacy_stock_only' => 'Legacy: Stock-Only (Fase AX-AY-BB)',
            'legacy_ab_ac' => 'Legacy: IHSG+Saham Crash (Fase AB/AC)',
            'ai_tp30' => 'AI Prediksi (TP30%/SL3%/40h)',
            'momentum' => 'Momentum (RSI>60) — EXPLORATORY',
            'bottom_rebound' => 'Bottom-Rebound (BUMI+DEWA)',
            'manual_discretionary' => 'Manual/Diskresi',
        ];
        $strategyBreakdown = [];
        foreach ($strategyLabels as $key => $label) {
            $group = $closed->where('strategy_label', $key);
            $groupOpen = $open->where('strategy_label', $key);
            if ($group->isEmpty() && $groupOpen->isEmpty()) {
                continue;
            }
            $groupWin = $group->where('pnl_total', '>', 0)->count();

            // Episode independence bukan cuma milik GABUNGAN -- strategi lain (terutama
            // legacy_stock_only/legacy_ab_ac, yang aturannya juga "beli pas jatuh tajam") sama
            // rentannya terhadap satu koreksi panjang tercatat sebagai banyak trade terpisah.
            $groupEpisodes = $this->groupIntoEpisodes($group);
            $groupEpisodeWins = collect($groupEpisodes)->filter(fn ($ep) => collect($ep)->avg('pnl_total') > 0);

            $strategyBreakdown[] = [
                'key' => $key,
                'label' => $label,
                'open' => $groupOpen->count(),
                'closed' => $group->count(),
                'win_rate' => $group->count() > 0 ? round($groupWin / $group->count() * 100, 1) : null,
                'total_pnl' => $group->sum('pnl_total'),
                'episode_count' => count($groupEpisodes),
                'episode_win_rate' => count($groupEpisodes) > 0
                    ? round($groupEpisodeWins->count() / count($groupEpisodes) * 100, 1)
                    : null,
            ];
        }

        // Fase CM: tabel "Riwayat Trading" render SEMUA closed trade tanpa pagination (374+ baris
        // dan terus tumbuh) -- terlalu berat untuk dipindai user. Dipisah dari $closed/$scope di
        // atas (yang tetap dipakai utuh untuk stats/episode -- itu WAJIB lihat semua data, tidak
        // boleh ikut kepotong pagination) -- filter+pagination cuma untuk tampilan tabel riwayat.
        $historyStrategy = $request->query('filter_strategy');
        $historyTicker = $request->query('filter_ticker');

        $history = $closed;
        if ($historyStrategy) {
            $history = $history->where('strategy_label', $historyStrategy);
        }
        if ($historyTicker) {
            $history = $history->where('ticker', $historyTicker);
        }
        $history = $history->values();

        $perPage = 30;
        $page = max(1, (int) $request->query('page', 1));
        $closedPage = new \Illuminate\Pagination\LengthAwarePaginator(
            $history->forPage($page, $perPage)->values(),
            $history->count(),
            $perPage,
            $page,
            ['path' => $request->url(), 'query' => $request->query()]
        );

        $historyStrategyOptions = $closed->pluck('strategy_label')->filter()->unique()->sort()->values();
        $historyTickerOptions = $closed->pluck('ticker')->unique()->sort()->values();

        // Fase CU: laporan portofolio ala StockBit (chart cumulative + leaderboard per saham).
        // SELALU GABUNGAN resmi, TIDAK ikut toggle $scope di atas -- user eksplisit pilih ini
        // supaya angkanya konsisten dengan kartu resmi lain, tidak ikut menggelembung kalau user
        // sedang lihat mode "Semua Strategi" di bagian lain halaman yang sama.
        $gabunganClosed = $closed->where('strategy_label', 'gabungan');
        $portfolioReport = $this->buildPortfolioReport($gabunganClosed);

        return view('trades.laporan', compact(
            'stats', 'closed', 'strategyBreakdown', 'monthlyBreakdown', 'scope',
            'closedPage', 'historyStrategy', 'historyTicker', 'historyStrategyOptions', 'historyTickerOptions',
            'portfolioReport'
        ));
    }

    /**
     * Fase CU: laporan portofolio ala StockBit -- diminta user setelah lihat referensi tab
     * "Portfolio" (return % vs IHSG) dan tab "Trade" (Rupiah kumulatif + leaderboard per saham).
     * Digabung jadi satu (user pilih "dua-duanya, ada toggle" lewat AskUserQuestion) supaya tidak
     * bikin 2 komponen terpisah yang isinya tumpang tindih.
     *
     * "Total Dividend Received" di referensi StockBit SENGAJA tidak diikutkan -- sistem ini tidak
     * melacak dividen sama sekali, menampilkan Rp0 di situ akan terbaca sebagai "belum ada dividen"
     * padahal kenyataannya "kita memang tidak mengukurnya". Diam-diam salah lebih buruk daripada
     * tidak ada elemen itu sama sekali.
     */
    private function buildPortfolioReport($gabunganClosed): array
    {
        $winners = $gabunganClosed->where('pnl_total', '>', 0);
        $losers = $gabunganClosed->where('pnl_total', '<=', 0);
        $realizedGain = (float) $winners->sum('pnl_total');
        $realizedLoss = (float) abs($losers->sum('pnl_total'));

        // Leaderboard per saham -- pnl_pct dihitung relatif ke TOTAL MODAL DIKERAHKAN utk ticker
        // itu (n_trade x Rp10jt LIVE_CAPITAL per trade, bukan compounding), konsisten dgn cara
        // Fase CI melaporkan "Total PnL / Total modal dikerahkan" -- bukan rata-rata pnl_percent
        // per trade (itu akan bias ke trade kecil yg persentasenya kebetulan besar).
        $leaderboard = $gabunganClosed->groupBy('ticker')->map(function ($rows, $ticker) {
            $pnl = (float) $rows->sum('pnl_total');
            $capitalDeployed = $rows->count() * self::CAPITAL_PER_TRADE;

            return [
                'ticker' => $ticker,
                'trades' => $rows->count(),
                'pnl' => $pnl,
                'pnl_pct' => $capitalDeployed > 0 ? round($pnl / $capitalDeployed * 100, 2) : 0,
            ];
        })->sortByDesc('pnl')->values()->all();

        return [
            'profit_factor' => $realizedLoss > 0 ? round($realizedGain / $realizedLoss, 2) : null,
            'realized_gain' => $realizedGain,
            'realized_loss' => $realizedLoss,
            'max_profit_trade' => $gabunganClosed->sortByDesc('pnl_total')->first(),
            'max_loss_trade' => $gabunganClosed->sortBy('pnl_total')->first(),
            'leaderboard' => $leaderboard,
            'chart' => $this->portfolioChartData($gabunganClosed),
        ];
    }

    private const CAPITAL_PER_TRADE = 10_000_000;

    /**
     * Bangun 2 seri chart: Rupiah kumulatif (realisasi tiap exit_date) dan IHSG (Yahoo Finance,
     * dinormalisasi 0% di hari trade pertama) -- 1 sumbu tanggal kalender yang sama, di-forward-
     * fill supaya garis tetap jalan di hari libur/akhir pekan (bukan putus-putus).
     */
    private function portfolioChartData($gabunganClosed): array
    {
        $trades = $gabunganClosed->sortBy(fn ($t) => $t->exit_date)->values();
        if ($trades->isEmpty()) {
            return ['labels' => [], 'portfolio_rp' => [], 'portfolio_pct' => [], 'ihsg_pct' => []];
        }

        $startDate = $trades->min(fn ($t) => $t->entry_date)->copy()->startOfDay();
        $endDate = now()->startOfDay();

        $pnlByDate = [];
        foreach ($trades as $t) {
            $key = $t->exit_date->format('Y-m-d');
            $pnlByDate[$key] = ($pnlByDate[$key] ?? 0) + (float) $t->pnl_total;
        }

        $ihsg = $this->fetchIhsgSeries();

        $labels = [];
        $portfolioRp = [];
        $portfolioPct = [];
        $ihsgPct = [];

        $cumulative = 0.0;
        $ihsgBase = null;
        $lastIhsg = null;

        for ($d = $startDate->copy(); $d->lte($endDate); $d->addDay()) {
            $key = $d->format('Y-m-d');
            if (isset($pnlByDate[$key])) {
                $cumulative += $pnlByDate[$key];
            }

            if (isset($ihsg[$key])) {
                $lastIhsg = $ihsg[$key];
                $ihsgBase ??= $lastIhsg;
            }

            $labels[] = $d->format('d M');
            $portfolioRp[] = round($cumulative, 0);
            $portfolioPct[] = round($cumulative / self::CAPITAL_PER_TRADE * 100, 2);
            $ihsgPct[] = ($ihsgBase && $lastIhsg) ? round(($lastIhsg / $ihsgBase - 1) * 100, 2) : null;
        }

        return compact('labels', 'portfolioRp', 'portfolioPct', 'ihsgPct');
    }

    /**
     * IHSG (^JKSE) daily close via endpoint publik Yahoo Finance yang sama dgn HttpMarketDataProvider
     * -- data/stocks/IHSG.csv statis SENGAJA tidak dipakai, ketinggalan ~3 minggu dari trade
     * terbaru (dicek langsung: berhenti 31 Jul, trade kita sampai 19 Agu). Cache 15 menit -- ini
     * request eksternal, jangan tembak tiap kali halaman laporan dibuka (pola sama Fase CT).
     */
    private function fetchIhsgSeries(): array
    {
        return Cache::store('file')->remember('trades:ihsg-series:v1', now()->addMinutes(15), function () {
            try {
                $resp = Http::withHeaders(['User-Agent' => 'Mozilla/5.0'])
                    ->timeout(15)
                    ->get('https://query2.finance.yahoo.com/v8/finance/chart/%5EJKSE', [
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
                    $series[$date] = (float) $close;
                }

                return $series;
            } catch (Throwable $e) {
                return [];
            }
        });
    }

    /**
     * Kelompokkan trade jadi episode: per ticker, urut tanggal entry, jeda <=15 hari kalender
     * = episode yang sama. Protokol yang sama dipakai di riset Python sesi ini (Fase AY/BK/BQ/BR)
     * -- port PHP-nya di sini supaya kartu web bisa menampilkan angka yang konsisten tanpa perlu
     * lompat ke skrip Python terpisah tiap kali user mau lihat.
     *
     * @return array<int, array<int, Trade>>
     */
    private function groupIntoEpisodes($trades): array
    {
        $episodes = [];
        foreach ($trades->groupBy('ticker') as $rows) {
            $sorted = $rows->sortBy('entry_date')->values();
            $current = [$sorted[0]];
            for ($i = 1; $i < $sorted->count(); $i++) {
                // Carbon 3: diffInDays() sekarang SIGNED by default (beda dari Carbon 2 yang
                // selalu absolut) -- karena $sorted[$i] (lebih baru) dibandingkan ke tanggal
                // yang lebih lama, hasilnya NEGATIF tanpa abs(), bikin gap 20 hari lolos sebagai
                // "<=15" dan episode yang harusnya terpisah malah tergabung.
                $gapDays = abs($sorted[$i]->entry_date->diffInDays($current[count($current) - 1]->entry_date));
                if ($gapDays > 15) {
                    $episodes[] = $current;
                    $current = [$sorted[$i]];
                } else {
                    $current[] = $sorted[$i];
                }
            }
            $episodes[] = $current;
        }

        return $episodes;
    }

    /**
     * Harga terkini + P&L berjalan untuk tiap posisi terbuka, dikunci per trade id.
     *
     * Di-cache per KODE SAHAM (bukan per trade) selama market.refresh_seconds: tanpa ini tiap
     * refresh halaman menembak Yahoo Finance sekali per posisi, dan dua posisi di saham yang sama
     * akan menembak dua kali untuk harga yang identik.
     *
     * Kegagalan quote TIDAK boleh menjatuhkan halaman -- kalau Yahoo mati / rate-limit, entri
     * untuk trade itu di-set null dan view menampilkan "harga tidak tersedia", bukan angka
     * tebakan. Menampilkan P&L palsu jauh lebih berbahaya daripada tidak menampilkan apa-apa.
     */
    private function livePnlFor($open): array
    {
        if ($open->isEmpty()) {
            return [];
        }

        $ttl = (int) config('market.refresh_seconds', 60);
        $service = app(LiveMarketDataService::class);
        $quotes = [];
        $result = [];

        foreach ($open as $trade) {
            $stock = $trade->stock;
            if (! $stock) {
                $result[$trade->id] = null;
                continue;
            }

            $code = $stock->code;
            if (! array_key_exists($code, $quotes)) {
                try {
                    $quotes[$code] = Cache::remember(
                        "trade-live-quote:{$code}",
                        $ttl,
                        fn () => $service->quote($stock)
                    );
                } catch (Throwable $e) {
                    $quotes[$code] = null;
                }
            }

            $quote = $quotes[$code];
            $last = $quote['last'] ?? null;
            $entry = (float) $trade->entry_price;

            if ($last === null || $entry <= 0) {
                $result[$trade->id] = null;
                continue;
            }

            $last = (float) $last;
            // lot_size menyimpan LEMBAR (bukan jumlah lot) -- konvensi yang sama dipakai
            // TradeController::store() dan jembatan SYNC_OPEN, lihat LEMBAR_PER_LOT.
            $shares = (int) $trade->lot_size;

            $result[$trade->id] = [
                'last' => $last,
                'pnl' => ($last - $entry) * $shares,
                'pnl_percent' => ($last - $entry) / $entry * 100,
                'is_live' => (bool) ($quote['is_live'] ?? false),
                'source' => $quote['source'] ?? null,
                'fetched_at' => $quote['fetched_at'] ?? null,
            ];
        }

        return $result;
    }

    // 1 Lot = 100 lembar -- standar papan perdagangan IDX sejak 2014.
    private const LEMBAR_PER_LOT = 100;

    public function store(Request $request)
    {
        $validated = $request->validate([
            'stock_id' => 'required|exists:stocks,id',
            'entry_price' => 'required|numeric|min:1',
            'stop_loss' => 'required|numeric|min:0',
            'target_1' => 'required|numeric|min:0',
            'target_2' => 'nullable|numeric|min:0',
            'entry_zone_low' => 'nullable|numeric|min:0',
            'entry_zone_high' => 'nullable|numeric|min:0',
            'lot' => 'required|integer|min:1',
            'entry_date' => 'required|date',
            'signal_quality' => 'nullable|string',
            'dss_score' => 'nullable|numeric',
            'dss_prediction' => 'nullable|string',
            'dss_confidence' => 'nullable|numeric',
            'rr_ratio' => 'nullable|numeric',
            'notes' => 'nullable|string|max:500',
        ]);

        // User input jumlah Lot (kebiasaan broker, mis. StockBit) -- disimpan ke kolom lot_size
        // sebagai lembar karena itu yang dipakai langsung oleh perhitungan PnL/position_value.
        $validated['lot_size'] = $validated['lot'] * self::LEMBAR_PER_LOT;
        unset($validated['lot']);

        $validated['user_id'] = auth()->id();
        $validated['status'] = 'open';
        $validated['result'] = 'open';
        // Kolom signal_quality NOT NULL tanpa default; form manual tidak selalu mengirimnya.
        $validated['signal_quality'] = $validated['signal_quality'] ?? 'manual';
        $validated['position_value'] = $validated['entry_price'] * $validated['lot_size'];
        // Fase CA: entry lewat form web = keputusan manual user, bukan sinyal otomatis GABUNGAN
        // -- TIDAK dihitung ke kartu ringkasan resmi (lihat TradeController::index()).
        $validated['strategy_label'] = 'manual_discretionary';

        Trade::create($validated);

        return redirect()->route('trades.index')->with('success', 'Trade berhasil dicatat!');
    }

    public function close(Request $request, Trade $trade)
    {
        if ($trade->user_id !== auth()->id()) {
            abort(403);
        }

        $validated = $request->validate([
            'exit_price' => 'required|numeric|min:0',
            'result' => 'required|in:hit_target_1,hit_target_2,stop_loss,manual_close',
            'notes' => 'nullable|string|max:500',
        ]);

        $trade->close($validated['exit_price'], $validated['result']);

        if (!empty($validated['notes'])) {
            $trade->update(['notes' => $validated['notes']]);
        }

        return redirect()->route('trades.index')->with('success', 'Trade ditutup!');
    }

    public function destroy(Trade $trade)
    {
        if ($trade->user_id !== auth()->id()) {
            abort(403);
        }
        $trade->delete();

        return redirect()->route('trades.index')->with('success', 'Trade dihapus.');
    }
}
