<?php

namespace App\Services;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use App\Models\UserWatchlist;
use App\Services\Analytics\DecisionSupportService;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Support\Collection;

class WatchlistService
{
    public function __construct(
        protected PriceSeriesService $priceSeriesService,
        protected SentimentPriceAnalyticsService $sentimentPriceAnalyticsService,
        protected DecisionSupportService $decisionSupportService
    ) {
    }

    public function getWatchlist(User $user)
    {
        return $user->watchlistStocks()->with(['latestPrice'])->get();
    }

    public function getWatchlistWithAnalytics(User $user, int $periodDays = 7): Collection
    {
        $stocks = $this->getWatchlist($user);

        return $stocks->map(function (Stock $stock) use ($periodDays) {
            $prices = $this->priceSeriesService->getSeries($stock, '1d', $periodDays + 5);
            $articles = NewsArticle::where('stock_id', $stock->id)
                ->where('published_at', '>=', now()->subDays($periodDays))
                ->latest('published_at')
                ->get();

            $analytics = $this->sentimentPriceAnalyticsService->analyze($stock, $prices, $articles, $periodDays);
            $decision = $this->decisionSupportService->analyze($stock, $prices, $articles, $analytics);

            $recentNegatives = $articles->where('sentiment_label', 'negative')
                ->where('published_at', '>=', now()->subDay())
                ->count();

            return [
                'stock' => $stock,
                'latest' => $stock->latestPrice,
                'analytics' => $analytics,
                'decision' => $decision,
                'sparkline' => collect($analytics['per_date_sentiment'] ?? [])->take(-7)->map(fn ($row) => $row['avg'])->values(),
                'negative_alert' => $recentNegatives >= 2,
                'negative_alert_count' => $recentNegatives,
            ];
        });
    }

    public function add(User $user, Stock $stock): void
    {
        UserWatchlist::firstOrCreate([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
        ]);
    }

    public function remove(User $user, Stock $stock): void
    {
        UserWatchlist::where('user_id', $user->id)
            ->where('stock_id', $stock->id)
            ->delete();
    }

    public function toggle(User $user, Stock $stock): bool
    {
        $existing = UserWatchlist::where('user_id', $user->id)
            ->where('stock_id', $stock->id)
            ->first();

        if ($existing) {
            $existing->delete();

            return false;
        }

        $this->add($user, $stock);

        return true;
    }
}
