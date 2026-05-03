<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Models\Trade;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

class TradeJournalController extends Controller
{
    /**
     * Display only the authenticated user's trade journal entries.
     */
    public function index(): View
    {
        $trades = Trade::query()
            ->where('user_id', auth()->id())
            ->latest('trade_date')
            ->latest()
            ->paginate(20);

        return view('trade-journal.index', compact('trades'));
    }

    /**
     * Show the trade journal creation form.
     */
    public function create(): View
    {
        return view('trade-journal.create');
    }

    /**
     * Store a validated trade journal entry for the authenticated user.
     */
    public function store(Request $request): RedirectResponse
    {
        $validated = $this->validateTrade($request);
        $stock = $this->resolveStock($validated['ticker']);

        Trade::create(array_merge($this->legacyTradeDefaults($validated, $stock), [
            'user_id' => auth()->id(),
            'stock_id' => $stock->id,
            'ticker' => strtoupper($validated['ticker']),
            'direction' => $validated['direction'],
            'entry_price' => $validated['entry_price'],
            'quantity' => $validated['quantity'],
            'lot_size' => $validated['quantity'],
            'trade_date' => $validated['trade_date'],
            'entry_date' => $validated['trade_date'],
            'notes' => $validated['notes'] ?? null,
            'status' => 'open',
            'result' => 'open',
        ]));

        return redirect()->route('trade-journal.index')->with('status', 'Trade journal berhasil dicatat.');
    }

    /**
     * Show the edit form for one owned trade journal entry.
     */
    public function edit(Trade $trade): View
    {
        $trade = $this->ownedTrade($trade);

        return view('trade-journal.edit', compact('trade'));
    }

    /**
     * Update one owned trade journal entry.
     */
    public function update(Request $request, Trade $trade): RedirectResponse
    {
        $trade = $this->ownedTrade($trade);
        $validated = $this->validateTrade($request);
        $stock = $this->resolveStock($validated['ticker']);

        $trade->update(array_merge($this->legacyTradeDefaults($validated, $stock), [
            'stock_id' => $stock->id,
            'ticker' => strtoupper($validated['ticker']),
            'direction' => $validated['direction'],
            'entry_price' => $validated['entry_price'],
            'quantity' => $validated['quantity'],
            'lot_size' => $validated['quantity'],
            'trade_date' => $validated['trade_date'],
            'entry_date' => $validated['trade_date'],
            'notes' => $validated['notes'] ?? null,
        ]));

        return redirect()->route('trade-journal.index')->with('status', 'Trade journal berhasil diperbarui.');
    }

    /**
     * Delete one owned trade journal entry.
     */
    public function destroy(Trade $trade): RedirectResponse
    {
        $this->ownedTrade($trade)->delete();

        return redirect()->route('trade-journal.index')->with('status', 'Trade journal berhasil dihapus.');
    }

    /**
     * Close one owned trade and calculate P&L using long/short direction.
     */
    public function close(Request $request, Trade $trade): RedirectResponse
    {
        $trade = $this->ownedTrade($trade);
        $validated = $request->validate([
            'exit_price' => ['required', 'numeric', 'min:0'],
        ]);

        $directionMultiplier = ($trade->direction ?? 'long') === 'short' ? -1 : 1;
        $quantity = (int) ($trade->quantity ?? $trade->lot_size ?? 1);
        $pnl = ((float) $validated['exit_price'] - (float) $trade->entry_price) * $quantity * $directionMultiplier;
        $pnlPercent = $trade->entry_price > 0
            ? round((((float) $validated['exit_price'] - (float) $trade->entry_price) / (float) $trade->entry_price) * 100 * $directionMultiplier, 2)
            : 0;

        $trade->update([
            'exit_price' => $validated['exit_price'],
            'exit_date' => now()->toDateString(),
            'closed_at' => now(),
            'status' => 'closed',
            'result' => $pnl >= 0 ? 'manual_close' : 'stop_loss',
            'pnl' => round($pnl, 2),
            'pnl_total' => round($pnl, 2),
            'pnl_per_share' => round(((float) $validated['exit_price'] - (float) $trade->entry_price) * $directionMultiplier, 2),
            'pnl_percent' => $pnlPercent,
        ]);

        return redirect()->route('trade-journal.index')->with('status', 'Trade journal berhasil ditutup.');
    }

    /**
     * Validate the common trade journal payload.
     *
     * @return array<string, mixed>
     */
    protected function validateTrade(Request $request): array
    {
        return $request->validate([
            'ticker' => ['required', 'string', 'max:10'],
            'entry_price' => ['required', 'numeric', 'min:0'],
            'quantity' => ['required', 'integer', 'min:1'],
            'direction' => ['required', 'in:long,short'],
            'trade_date' => ['required', 'date'],
            'notes' => ['nullable', 'string'],
        ]);
    }

    /**
     * Resolve or create a stock record for journal entries submitted by ticker.
     */
    protected function resolveStock(string $ticker): Stock
    {
        $code = strtoupper($ticker);

        return Stock::firstOrCreate(
            ['code' => $code],
            [
                'company_name' => $code.' Tbk',
                'exchange' => 'IDX',
                'is_active' => true,
            ]
        );
    }

    /**
     * Provide required legacy trade fields so `/trade-journal` can share the existing table.
     *
     * @return array<string, mixed>
     */
    protected function legacyTradeDefaults(array $validated, Stock $stock): array
    {
        $entry = (float) $validated['entry_price'];
        $stopLoss = $validated['direction'] === 'long' ? max(0, $entry * 0.95) : $entry * 1.05;
        $target = $validated['direction'] === 'long' ? $entry * 1.1 : max(0, $entry * 0.9);

        return [
            'signal_quality' => 'journal',
            'stop_loss' => round($stopLoss, 2),
            'target_1' => round($target, 2),
            'target_2' => null,
            'rr_ratio' => null,
            'position_value' => $entry * (int) $validated['quantity'],
        ];
    }

    /**
     * Enforce ownership for route model bound trade journal entries.
     */
    protected function ownedTrade(Trade $trade): Trade
    {
        if ($trade->user_id !== auth()->id()) {
            abort(403);
        }

        return $trade;
    }
}
