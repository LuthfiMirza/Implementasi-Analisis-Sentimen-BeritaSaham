<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Analytics\DecisionSupportService;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use App\Services\Prediction\FeatureBuilderService;
use App\Services\Prediction\PredictionEngineManager;
use App\Services\Sentiment\SentimentSummaryService;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Http\Request;

class AnalyticsController extends Controller
{
    public function __construct(
        protected SentimentSummaryService $sentimentSummaryService,
        protected PriceSeriesService $priceSeriesService,
        protected DecisionSupportService $decisionSupportService,
        protected SentimentPriceAnalyticsService $sentimentPriceAnalyticsService,
        protected FeatureBuilderService $featureBuilderService,
        protected PredictionEngineManager $predictionEngineManager,
    ) {
    }

    public function index(Request $request)
    {
        $stockCode = $request->query('code', config('dashboard.default_stock', 'BBCA'));
        $period = (int) $request->query('period', 30);
        $period = in_array($period, [7, 30, 90]) ? $period : 30;
        $includeMacroNews = $request->boolean('include_macro_news', true);
        $priceLimit = max(60, $period);
        $stock = Stock::where('code', $stockCode)->firstOrFail();

        $articles = NewsArticle::with('stock')
            ->forStockContext($stock, $includeMacroNews)
            ->whereNotNull('published_at')
            ->where('published_at', '>=', now()->subDays($period))
            ->latest('published_at')
            ->get();

        $summary = $this->sentimentSummaryService->summarize($articles);
        $priceSeries = $this->priceSeriesService->getSeries($stock, '1d', $priceLimit)->values();
        $liveQuote = app(\App\Services\MarketData\LiveMarketDataService::class)->quote($stock);
        $analytics = $this->sentimentPriceAnalyticsService->analyze($stock, $priceSeries, $articles, $period);
        $decision = $this->decisionSupportService->analyze($stock, $priceSeries, $articles, $analytics);
        $features = $this->featureBuilderService->build($stock, $priceSeries, $articles, $analytics, $period);
        $prediction = $this->predictionEngineManager->predict($features);

        $perDate = collect($analytics['per_date_sentiment'] ?? []);
        $labels = $priceSeries->map(fn ($p) => optional($p->price_date)->toDateString())->values();
        $chartData = [
            'labels' => $labels->map(fn ($d) => \Carbon\Carbon::parse($d)->format('d M')),
            'raw_dates' => $labels,
            'prices' => $priceSeries->map(fn ($p) => $p->close)->values(),
            'sentiments' => $labels->map(fn ($d) => $perDate[$d]['avg'] ?? null),
            'volume' => $labels->map(fn ($d) => $perDate[$d]['count'] ?? 0),
            'events' => $analytics['event_study'] ?? [],
        ];

        $topStocks = NewsArticle::selectRaw('stock_id, count(*) as total')
            ->whereNotNull('stock_id')
            ->groupBy('stock_id')
            ->with('stock')
            ->orderByDesc('total')
            ->limit(5)
            ->get();

        $topPositiveArticles = $articles->where('sentiment_label', 'positive')->sortByDesc('sentiment_score')->take(3);
        $topRiskArticles = $articles->where('sentiment_label', 'negative')->sortBy('sentiment_score')->take(3);
        $priceMeta = $this->priceSeriesService->latestWithChange($stock, '1d');

        return view('analytics.index', [
            'stock' => $stock,
            'summary' => $summary,
            'articles' => $articles->take(15),
            'topStocks' => $topStocks,
            'stocks' => Stock::orderBy('code')->get(),
            'chartData' => $chartData,
            'period' => $period,
            'includeMacroNews' => $includeMacroNews,
            'decision' => $decision,
            'analytics' => $analytics,
            'prediction' => $prediction,
            'prices' => $priceSeries,
            'topPositiveArticles' => $topPositiveArticles,
            'topRiskArticles' => $topRiskArticles,
            'latestPrice' => $priceMeta['latest'],
            'priceChange' => $priceMeta['change_pct'],
            'liveQuote' => $liveQuote,
        ]);
    }
}
