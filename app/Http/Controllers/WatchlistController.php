<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\Prediction\ResearchRankingService;
use App\Services\WatchlistService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;

class WatchlistController extends Controller
{
    public function __construct(
        protected WatchlistService $watchlistService,
        protected ResearchRankingService $researchRankingService,
    ) {}

    public function index(Request $request)
    {
        $search = (string) $request->query('q', '');
        $items = $this->watchlistService->getWatchlistWithAnalytics($request->user(), 14)
            ->when($search !== '', fn ($collection) => $collection->filter(function ($item) use ($search) {
                $stock = $item['stock'];
                $haystack = strtolower($stock->code.' '.$stock->company_name);
                return str_contains($haystack, strtolower($search));
            }))
            ->values();
        $stocks = Stock::orderBy('code')->get();
        $rankingCodes = $items->map(fn ($item) => $item['stock']->code)->all();
        $technicalRanking = Cache::remember(
            $this->technicalRankingCacheKey($request->user()?->id, $rankingCodes),
            now()->addMinutes(5),
            fn (): array => $this->researchRankingService->getRanking($rankingCodes)
        );

        return view('watchlist.index', [
            'items' => $items,
            'stocks' => $stocks,
            'search' => $search,
            'technicalRanking' => $technicalRanking,
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

    protected function technicalRankingCacheKey(?int $userId, array $codes): string
    {
        $normalizedCodes = collect($codes)
            ->map(fn ($code) => strtoupper(trim((string) $code)))
            ->filter()
            ->sort()
            ->values()
            ->implode(',');

        return 'watchlist:technical-ranking:user:'.($userId ?? 'guest').':'.md5($normalizedCodes);
    }
}
