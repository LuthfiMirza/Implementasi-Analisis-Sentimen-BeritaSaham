<?php

namespace App\Http\Controllers;

use App\Models\BsjpTradeLog;
use App\Models\Stock;
use App\Services\Trading\SignalRadarService;
use Carbon\Carbon;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

class BsjpTradeController extends Controller
{
    /**
     * Tampilkan dasbor tracker live trade BSJP (Beli Sore Jual Pagi).
     */
    public function index(Request $request, SignalRadarService $radarService): View
    {
        $baseCapital = (float) config('trading.bsjp_default_capital', 20000000.00); // Rp 20 Jt default

        $closedTrades = BsjpTradeLog::closed()
            ->orderByDesc('exited_at')
            ->orderByDesc('id')
            ->get();

        $openPositions = BsjpTradeLog::open()
            ->orderByDesc('entry_at')
            ->get();

        $pendingSignals = BsjpTradeLog::pending()
            ->orderByDesc('signal_date')
            ->get();

        $totalClosed = $closedTrades->count();
        $wins = $closedTrades->where('net_pnl_rp', '>', 0);
        $losses = $closedTrades->where('net_pnl_rp', '<=', 0);
        $winRate = $totalClosed > 0 ? round(($wins->count() / $totalClosed) * 100, 1) : 0.0;
        $totalRealizedPnl = (float) $closedTrades->sum('net_pnl_rp');
        $currentCapital = $baseCapital + $totalRealizedPnl;
        $totalCapitalGrowthPct = $baseCapital > 0 ? round(($totalRealizedPnl / $baseCapital) * 100, 2) : 0.0;

        $stats = [
            'base_capital' => $baseCapital,
            'current_capital' => $currentCapital,
            'total_realized_pnl' => $totalRealizedPnl,
            'total_capital_growth_pct' => $totalCapitalGrowthPct,
            'total_trades' => $totalClosed,
            'win_trades' => $wins->count(),
            'loss_trades' => $losses->count(),
            'win_rate' => $winRate,
            'open_count' => $openPositions->count(),
            'pending_count' => $pendingSignals->count(),
        ];

        return view('trades.bsjp_tracker', compact('stats', 'openPositions', 'closedTrades', 'pendingSignals'));
    }

    /**
     * Catat eksekusi beli di Pre-Closing (15:50 WIB) dengan modal Rp 20 Juta.
     */
    public function buy(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'ticker' => ['required', 'string', 'max:16'],
            'signal_date' => ['nullable', 'date'],
            'entry_price' => ['required', 'numeric', 'min:1'],
            'capital' => ['nullable', 'numeric', 'min:100000'],
            'lots' => ['nullable', 'integer', 'min:1'],
            'category' => ['nullable', 'string', 'in:sweetspot,rocket'],
            'target_tp' => ['nullable', 'numeric'],
            'stop_loss' => ['nullable', 'numeric'],
            'notes' => ['nullable', 'string'],
        ]);

        $ticker = strtoupper($data['ticker']);
        $signalDate = ! empty($data['signal_date']) ? Carbon::parse($data['signal_date'])->toDateString() : now('Asia/Jakarta')->toDateString();
        $entryPrice = (float) $data['entry_price'];
        $capital = (float) ($data['capital'] ?? 20000000.00);

        // Jika lots tidak diisi manual, hitung otomatis dari alokasi modal
        $lots = isset($data['lots']) && $data['lots'] > 0
            ? (int) $data['lots']
            : BsjpTradeLog::calculateLots($capital, $entryPrice);

        $stock = Stock::where('code', $ticker)->first();
        $stockName = $stock ? $stock->company_name : ($ticker . ' Tbk.');

        $targetTp = (float) ($data['target_tp'] ?? round($entryPrice * 1.025, 0));
        $stopLoss = (float) ($data['stop_loss'] ?? round($entryPrice * 0.97, 0));

        $log = BsjpTradeLog::updateOrCreate(
            [
                'signal_date' => $signalDate,
                'ticker' => $ticker,
            ],
            [
                'stock_name' => $stockName,
                'category' => $data['category'] ?? 'sweetspot',
                'signal_price' => $entryPrice,
                'target_tp' => $targetTp,
                'stop_loss' => $stopLoss,
                'status' => 'OPEN',
                'capital_allocated' => $capital,
                'lots' => $lots,
                'entry_price' => $entryPrice,
                'entry_at' => now('Asia/Jakarta'),
                'notes' => $data['notes'] ?? null,
            ]
        );

        $cost = number_format($lots * 100 * $entryPrice, 0, ',', '.');
        return back()->with('status', "🛒 Berhasil mencatat BELI BSJP {$ticker} @ Rp " . number_format($entryPrice, 0, ',', '.') . " sebanyak {$lots} lot (Nilai: Rp {$cost}). Siap jual di Open 09:00 WIB!");
    }

    /**
     * Catat penjualan posisi BSJP (di Open 09:00 WIB, kena TP, atau Stop Loss).
     */
    public function sell(Request $request, BsjpTradeLog $log): RedirectResponse
    {
        $data = $request->validate([
            'exit_price' => ['required', 'numeric', 'min:1'],
            'exit_type' => ['nullable', 'string', 'in:OPEN_MARKET,TARGET_TP,STOP_LOSS,MANUAL'],
            'exited_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string'],
        ]);

        $exitPrice = (float) $data['exit_price'];
        $exitType = $data['exit_type'] ?? 'OPEN_MARKET';
        $exitedAt = !empty($data['exited_at']) ? Carbon::parse($data['exited_at']) : now('Asia/Jakarta');

        $pnl = BsjpTradeLog::calculatePnl($log->entry_price, $exitPrice, $log->lots);

        $log->update([
            'exit_price' => $exitPrice,
            'exited_at' => $exitedAt,
            'exit_type' => $exitType,
            'gross_pnl_pct' => $pnl['gross_pnl_pct'],
            'net_pnl_pct' => $pnl['net_pnl_pct'],
            'net_pnl_rp' => $pnl['net_pnl_rp'],
            'status' => 'CLOSED',
            'notes' => $data['notes'] ?? $log->notes,
        ]);

        $emoji = $pnl['net_pnl_rp'] > 0 ? '🟢 CUAN' : ($pnl['net_pnl_rp'] < 0 ? '🔴 LOSS' : '⚪ BEP');
        $pnlStr = sprintf('%+.2f%% (Rp %s)', $pnl['net_pnl_pct'], number_format($pnl['net_pnl_rp'], 0, ',', '.'));

        return back()->with('status', "{$emoji} Penjualan BSJP {$log->ticker} berhasil dicatat @ Rp " . number_format($exitPrice, 0, ',', '.') . ". Hasil Bersih: {$pnlStr}.");
    }

    /**
     * Lewati sinyal (tidak jadi dieksekusi).
     */
    public function skip(Request $request, BsjpTradeLog $log): RedirectResponse
    {
        $log->update([
            'status' => 'SKIPPED',
        ]);

        return back()->with('status', "⏭️ Sinyal {$log->ticker} ({$log->signal_date->format('d M')}) ditandai LEWATI (SKIPPED).");
    }
}
