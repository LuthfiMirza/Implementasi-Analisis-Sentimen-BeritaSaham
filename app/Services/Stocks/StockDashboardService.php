<?php

namespace App\Services\Stocks;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\SystemSetting;
use App\Models\User;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\News\NewsAggregationService;
use App\Services\Sentiment\SentimentSummaryService;
use App\Services\WatchlistService;
use Illuminate\Database\Eloquent\ModelNotFoundException;

class StockDashboardService
{
    public function __construct(
        protected PriceSeriesService $priceSeriesService,
        protected SentimentSummaryService $sentimentSummaryService,
        protected NewsAggregationService $newsAggregationService,
        protected WatchlistService $watchlistService,
        protected LiveMarketDataService $liveMarketDataService
    ) {
    }

    public function getDashboardData(?string $stockCode, ?User $user = null, string $interval = '1d'): array
    {
        $stock = $stockCode
            ? Stock::where('code', $stockCode)->first()
            : Stock::where('is_active', true)->orderBy('code')->first();

        if (! $stock) {
            throw new ModelNotFoundException('Saham tidak ditemukan');
        }

        if (! NewsArticle::where('stock_id', $stock->id)->exists()) {
            $this->newsAggregationService->refreshFromProvider($stock, 5);
        }

        $chartMode = data_get(SystemSetting::where('key', 'stock_chart_mode')->first(), 'value.value')
            ?? config('dashboard.stock_chart_mode', env('STOCK_CHART_MODE', 'tradingview'));

        $priceSeries = $this->priceSeriesService->getSeries($stock, $interval, 120);
        $liveQuote = $this->liveMarketDataService->quote($stock);
        $priceMeta = $this->priceSeriesService->latestWithChange($stock, $interval);
        if ($liveQuote) {
            $priceMeta['live_quote'] = $this->castQuote($liveQuote);
        }
        $news = $this->newsAggregationService->fetchLatestArticles($stock, 10);
        $sentimentSummary = $this->sentimentSummaryService->summarize($news);
        $insight = $this->sentimentSummaryService->generateInsight($stock->code, $sentimentSummary, $priceMeta['change_pct']);
        $watchlistInsights = $user ? $this->watchlistService->getWatchlistWithAnalytics($user, 7) : collect();
        $alerts = $watchlistInsights->filter(fn ($row) => $row['negative_alert'])->values();

        return [
            'stock' => $stock,
            'price_series' => $priceSeries,
            'latest_price' => $priceMeta['latest'],
            'price_change_pct' => $priceMeta['change_pct'],
            'live_quote' => $priceMeta['live_quote'] ?? null,
            'news' => $news,
            'sentiment_summary' => $sentimentSummary,
            'insight' => $insight,
            'chart_mode' => $chartMode,
            'watchlist' => $user ? $this->watchlistService->getWatchlist($user) : collect(),
            'watchlist_insights' => $watchlistInsights,
            'watchlist_alerts' => $alerts,
        ];
    }

    protected function castQuote(?array $quote): ?array
    {
        if (! $quote) {
            return null;
        }

        return [
            'stock_code' => $quote['stock_code'] ?? null,
            'open' => isset($quote['open']) ? (float) $quote['open'] : null,
            'high' => isset($quote['high']) ? (float) $quote['high'] : null,
            'low' => isset($quote['low']) ? (float) $quote['low'] : null,
            'close' => isset($quote['close']) ? (float) $quote['close'] : null,
            'last' => isset($quote['last']) ? (float) $quote['last'] : null,
            'volume' => isset($quote['volume']) ? (int) $quote['volume'] : null,
            'change' => $quote['change'] ?? null,
            'change_percent' => $quote['change_percent'] ?? null,
            'source' => $quote['source'] ?? null,
            'is_live' => $quote['is_live'] ?? false,
            'fetched_at' => $quote['fetched_at'] ?? null,
        ];
    }
}
