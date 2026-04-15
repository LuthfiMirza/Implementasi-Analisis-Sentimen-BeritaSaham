<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Models\Trade;
use Illuminate\Http\Request;

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

        $stats = [
            'total' => $trades->count(),
            'open' => $open->count(),
            'closed' => $closed->count(),
            'win' => $closed->whereIn('result', ['hit_target_1', 'hit_target_2'])->count(),
            'loss' => $closed->where('result', 'stop_loss')->count(),
            'win_rate' => $closed->count() > 0
                ? round($closed->whereIn('result', ['hit_target_1', 'hit_target_2'])->count() / $closed->count() * 100, 1)
                : 0,
            'total_pnl' => $closed->sum('pnl_total'),
            'avg_rr' => $closed->count() > 0 ? round($closed->avg('actual_rr'), 2) : 0,
            'avg_holding' => $closed->count() > 0 ? round($closed->avg('holding_days'), 1) : 0,
            'best_trade' => $closed->sortByDesc('pnl_total')->first(),
            'worst_trade' => $closed->sortBy('pnl_total')->first(),
            'expectancy' => 0,
        ];

        $avgWin = $closed->whereIn('result', ['hit_target_1', 'hit_target_2'])->avg('pnl_percent') ?? 0;
        $avgLoss = abs($closed->where('result', 'stop_loss')->avg('pnl_percent') ?? 0);
        $winRate = $stats['win_rate'] / 100;
        $stats['expectancy'] = round(($winRate * $avgWin) - ((1 - $winRate) * $avgLoss), 2);

        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        return view('trades.index', compact('trades', 'stats', 'open', 'closed', 'stocks'));
    }

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
            'lot_size' => 'required|integer|min:1',
            'entry_date' => 'required|date',
            'signal_quality' => 'nullable|string',
            'dss_score' => 'nullable|numeric',
            'dss_prediction' => 'nullable|string',
            'dss_confidence' => 'nullable|numeric',
            'rr_ratio' => 'nullable|numeric',
            'notes' => 'nullable|string|max:500',
        ]);

        $validated['user_id'] = auth()->id();
        $validated['status'] = 'open';
        $validated['result'] = 'open';
        $validated['position_value'] = $validated['entry_price'] * $validated['lot_size'];

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
