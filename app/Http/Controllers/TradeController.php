<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Models\Trade;
use App\Services\MarketData\LiveMarketDataService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Throwable;

class TradeController extends Controller
{
    public function index(Request $request)
    {
        $trades = Trade::with('stock')
            ->where('user_id', auth()->id())
            ->orderByDesc('entry_date')
            ->get();

        $closed = $trades->where('status', 'closed');
        $open = $trades->where('status', 'open');

        // Fase CA: kartu ringkasan RESMI cuma dihitung dari strategy_label='gabungan' -- 3 aturan
        // drawdown-bounce lama (legacy_stock_only/legacy_ab_ac/GABUNGAN) TERBUKTI tumpang tindih
        // periode untuk saham yang sama (dicek langsung dari notes backfill: "ada tumpang tindih
        // periode dengan catatan lama... user pilih tetap masukkan data baru ini berdampingan").
        // Menjumlahkan ketiganya dulu (versi sebelum Fase CA) berisiko menghitung untung yang
        // SAMA berkali-kali dengan aturan berbeda. GABUNGAN (Fase BK, aturan yang live SEKARANG)
        // dijadikan satu-satunya acuan resmi; sisanya tetap tersimpan utuh (TIDAK dihapus) sebagai
        // arsip riset, ditampilkan terpisah lewat $strategyBreakdown di bawah.
        $officialClosed = $closed->where('strategy_label', 'gabungan');

        // Menang/kalah dari PnL AKTUAL, bukan dari kategori `result` -- exit berbasis waktu
        // (manual_close, mis. aturan drawdown-bounce Fase AB/AC) valid juga dan sebelumnya
        // hilang sama sekali dari Win Rate karena bukan hit_target_1/2 maupun stop_loss.
        $winners = $officialClosed->where('pnl_total', '>', 0);
        $losers = $officialClosed->where('pnl_total', '<=', 0);

        $stats = [
            'total' => $trades->where('strategy_label', 'gabungan')->count(),
            'open' => $open->where('strategy_label', 'gabungan')->count(),
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

        // Riwayat strategi LAIN (bukan GABUNGAN) -- ditampilkan terpisah, TIDAK ikut kartu resmi
        // di atas, supaya kelihatan tapi tidak tercampur/menggelembungkan angka utama.
        $strategyLabels = [
            'legacy_stock_only' => 'Legacy: Stock-Only (Fase AX-AY-BB)',
            'legacy_ab_ac' => 'Legacy: IHSG+Saham Crash (Fase AB/AC)',
            'ai_tp30' => 'AI Prediksi (TP30%/SL3%/40h)',
            'momentum' => 'Momentum (RSI>60) — EXPLORATORY',
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
            $strategyBreakdown[] = [
                'key' => $key,
                'label' => $label,
                'open' => $groupOpen->count(),
                'closed' => $group->count(),
                'win_rate' => $group->count() > 0 ? round($groupWin / $group->count() * 100, 1) : null,
                'total_pnl' => $group->sum('pnl_total'),
            ];
        }

        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        $live = $this->livePnlFor($open);

        return view('trades.index', compact('trades', 'stats', 'open', 'closed', 'stocks', 'live', 'strategyBreakdown'));
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
