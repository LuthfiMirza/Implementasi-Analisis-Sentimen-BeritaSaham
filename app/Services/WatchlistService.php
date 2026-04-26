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
use Illuminate\Support\Facades\Cache;

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
        $negativeAlerts = $this->getNegativeAlerts($user)->keyBy(fn (array $row) => (int) $row['stock']->id);

        return $stocks->map(function (Stock $stock) use ($user, $periodDays, $negativeAlerts) {
            $cached = Cache::remember(
                $this->watchlistAnalyticsCacheKey($user->id, $stock->id),
                now()->addMinutes(5),
                function () use ($stock, $periodDays): array {
                    $prices = $this->priceSeriesService->getSeries($stock, '1d', $periodDays + 5);
                    $articles = NewsArticle::where('stock_id', $stock->id)
                        ->where('published_at', '>=', now()->subDays($periodDays))
                        ->latest('published_at')
                        ->get();

                    $analytics = $this->sentimentPriceAnalyticsService->analyze($stock, $prices, $articles, $periodDays);
                    $decision = $this->decisionSupportService->analyze($stock, $prices, $articles, $analytics);

                    return [
                        'analytics' => $analytics,
                        'decision' => $decision,
                        'sparkline' => collect($analytics['per_date_sentiment'] ?? [])->take(-7)->map(fn ($row) => $row['avg'])->values()->all(),
                    ];
                }
            );

            $negativeAlert = $negativeAlerts->get($stock->id);

            return [
                'stock' => $stock,
                'latest' => $stock->latestPrice,
                'analytics' => $cached['analytics'] ?? [],
                'decision' => $cached['decision'] ?? [],
                'sparkline' => collect($cached['sparkline'] ?? []),
                'negative_alert' => $negativeAlert !== null,
                'negative_alert_count' => (int) ($negativeAlert['negative_alert_count'] ?? 0),
            ];
        });
    }

    public function getNegativeAlerts(User $user, int $hours = 24, int $threshold = 2): Collection
    {
        $rows = Cache::remember(
            "watchlist:negative-alerts:user:{$user->id}",
            now()->addMinutes(2),
            function () use ($user, $hours, $threshold): array {
                $stocks = $this->getWatchlist($user)->keyBy('id');
                if ($stocks->isEmpty()) {
                    return [];
                }

                return NewsArticle::query()
                    ->selectRaw('stock_id, COUNT(*) as negative_alert_count')
                    ->whereIn('stock_id', $stocks->keys())
                    ->where('sentiment_label', 'negative')
                    ->where('published_at', '>=', now()->subHours($hours))
                    ->groupBy('stock_id')
                    ->havingRaw('COUNT(*) >= ?', [$threshold])
                    ->get()
                    ->map(fn ($row): array => [
                        'stock_id' => (int) $row->stock_id,
                        'negative_alert_count' => (int) $row->negative_alert_count,
                    ])
                    ->filter()
                    ->values()
                    ->all();
            }
        );

        $stocks = $this->getWatchlist($user)->keyBy('id');

        return collect($rows)
            ->map(function ($row) use ($stocks): ?array {
                $stockId = (int) data_get($row, 'stock_id');
                $stock = $stocks->get($stockId);

                if (! $stock) {
                    return null;
                }

                return [
                    'stock' => $stock,
                    'negative_alert' => true,
                    'negative_alert_count' => (int) data_get($row, 'negative_alert_count', 0),
                ];
            })
            ->filter()
            ->values();
    }

    public function add(User $user, Stock $stock): void
    {
        UserWatchlist::firstOrCreate([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
        ]);

        Cache::forget($this->watchlistAnalyticsCacheKey($user->id, $stock->id));
        Cache::forget("watchlist:negative-alerts:user:{$user->id}");
    }

    public function remove(User $user, Stock $stock): void
    {
        UserWatchlist::where('user_id', $user->id)
            ->where('stock_id', $stock->id)
            ->delete();

        Cache::forget($this->watchlistAnalyticsCacheKey($user->id, $stock->id));
        Cache::forget("watchlist:negative-alerts:user:{$user->id}");
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

    protected function watchlistAnalyticsCacheKey(int $userId, int $stockId): string
    {
        return "watchlist_analytics_{$userId}_{$stockId}";
    }
}
