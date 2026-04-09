<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\WatchlistService;
use Illuminate\Http\Request;

class WatchlistController extends Controller
{
    public function __construct(protected WatchlistService $watchlistService)
    {
    }

    public function index(Request $request)
    {
        $search = (string) $request->query('q', '');
        $items = $this->watchlistService->getWatchlistWithAnalytics($request->user(), 14)
            ->when($search !== '', fn ($collection) => $collection->filter(function ($item) use ($search) {
                $stock = $item['stock'];
                $haystack = strtolower($stock->code.' '.$stock->company_name);
                return str_contains($haystack, strtolower($search));
            }));
        $stocks = Stock::orderBy('code')->get();

        return view('watchlist.index', [
            'items' => $items,
            'stocks' => $stocks,
            'search' => $search,
        ]);
    }

    public function store(Request $request)
    {
        $validated = $request->validate([
            'stock_id' => ['required', 'exists:stocks,id'],
        ]);

        $stock = Stock::findOrFail($validated['stock_id']);
        $this->watchlistService->add($request->user(), $stock);

        return back()->with('status', "{$stock->code} ditambahkan ke watchlist.");
    }

    public function destroy(Stock $stock, Request $request)
    {
        $this->watchlistService->remove($request->user(), $stock);

        return back()->with('status', "{$stock->code} dihapus dari watchlist.");
    }
}
