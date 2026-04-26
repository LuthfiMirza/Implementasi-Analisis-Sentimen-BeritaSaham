<?php

namespace App\Services\Analytics;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Prediction\FeatureBuilderService;
use App\Services\Prediction\PredictionEngineManager;
use App\Services\Stocks\PriceSeriesService;
use Carbon\Carbon;
use Illuminate\Support\Collection;

class EvaluationReportService
{
    public function __construct(
        protected PriceSeriesService $priceSeriesService,
        protected SentimentPriceAnalyticsService $analyticsService,
        protected DecisionSupportService $decisionSupportService,
        protected FeatureBuilderService $featureBuilderService,
        protected PredictionEngineManager $predictionEngineManager
    ) {
    }

    public function generate(
        Stock $stock,
        int $period = 30,
        bool $includeMacroNews = true,
        ?bool $macroRegulatorySignal = null
    ): array
    {
        $period = max(3, $period);
        $prices = $this->priceSeriesService->getSeries($stock, '1d', $period + 5)->values();
        $windowEnd = $this->resolveWindowEnd($stock, $prices, $includeMacroNews);
        $windowStart = $windowEnd->copy()->subDays($period - 1)->startOfDay();

        $articles = NewsArticle::forStockContext($stock, $includeMacroNews)
            ->whereNotNull('published_at')
            ->whereBetween('published_at', [$windowStart, $windowEnd->copy()->endOfDay()])
            ->latest('published_at')
            ->get();

        $analytics = $this->analyticsService->analyze(
            $stock,
            $prices,
            $articles,
            $period,
            null,
            $macroRegulatorySignal
        );
        $decision = $this->decisionSupportService->analyze($stock, $prices, $articles, $analytics);

        $features = $this->featureBuilderService->build($stock, $prices, $articles, $analytics, $period);
        $prediction = $this->predictionEngineManager->predict($features);

        $sentimentStats = $this->sentimentStats($articles);

        return [
            'stock' => [
                'code' => $stock->code,
                'name' => $stock->company_name,
            ],
            'period_days' => $period,
            'data_points' => [
                'price_points' => $prices->count(),
                'article_count' => $articles->count(),
                'include_macro_news' => $includeMacroNews,
                'macro_regulatory_signal_enabled' => (bool) ($analytics['macro_regulatory_signal']['enabled'] ?? false),
            ],
            'sentiment' => [
                'average' => $analytics['average_sentiment'],
                'weighted' => $analytics['weighted_sentiment'],
                'dominance' => $analytics['sentiment_dominance'],
                'method_distribution' => $sentimentStats['method_distribution'],
                'python_usage_rate' => $sentimentStats['python_usage_rate'],
                'fallback_rate' => $sentimentStats['fallback_rate'],
                'avg_confidence' => $sentimentStats['avg_confidence'],
            ],
            'analytics' => [
                'same_day_correlation' => $analytics['same_day_correlation'],
                'lag_correlations' => $analytics['lag_correlations'],
                'event_study' => $analytics['event_study'],
                'volume_impact' => $analytics['volume_impact'],
                'price_trend' => $analytics['price_trend'],
                'sentiment_trend' => $analytics['sentiment_trend'],
                'cumulative_return' => $analytics['cumulative_return'],
                'volatility' => $analytics['volatility'],
            ],
            'macro_regulatory' => $analytics['macro_regulatory_signal'],
            'decision' => [
                'status' => $decision['status'],
                'confidence' => $decision['confidence'],
                'final_score' => $decision['final_score'],
                'final_score_before_macro' => $decision['final_score_before_macro'] ?? $decision['final_score'],
                'macro_regulatory_adjusted' => (bool) ($decision['macro_regulatory_adjusted'] ?? false),
            ],
            'prediction' => $prediction,
            'narrative' => $this->narrative(
                $analytics,
                $decision,
                $prediction,
                $sentimentStats,
                $analytics['macro_regulatory_signal'] ?? []
            ),
        ];
    }

    protected function resolveWindowEnd(Stock $stock, Collection $prices, bool $includeMacroNews): Carbon
    {
        $latestPriceDate = $prices->last()?->price_date;
        $latestArticleDate = NewsArticle::forStockContext($stock, $includeMacroNews)
            ->whereNotNull('published_at')
            ->max('published_at');

        $candidates = collect([$latestPriceDate, $latestArticleDate])
            ->filter()
            ->map(fn ($value) => $value instanceof Carbon ? $value->copy() : Carbon::parse($value));

        if ($candidates->isEmpty()) {
            return now();
        }

        return $candidates
            ->sortBy(fn (Carbon $date) => $date->getTimestamp())
            ->last()
            ->copy();
    }

    protected function sentimentStats(Collection $articles): array
    {
        $total = max(1, $articles->count());
        $distribution = $articles->groupBy('sentiment_method')->map->count()->toArray();
        $python = $distribution['python'] ?? 0;
        $fallback = ($distribution['hybrid_fallback'] ?? 0) + ($distribution['rule_based'] ?? 0);

        return [
            'method_distribution' => $distribution,
            'python_usage_rate' => round($python / $total, 3),
            'fallback_rate' => round($fallback / $total, 3),
            'avg_confidence' => $articles->avg('sentiment_confidence') ? round((float) $articles->avg('sentiment_confidence'), 2) : null,
        ];
    }

    protected function narrative(
        array $analytics,
        array $decision,
        array $prediction,
        array $sentimentStats,
        array $macroSignal = []
    ): string
    {
        $avg = $analytics['average_sentiment'];
        $trend = $analytics['sentiment_trend'];
        $priceTrend = $analytics['price_trend'];
        $corr = $analytics['same_day_correlation'];
        $lag1 = $analytics['lag_correlations']['h1'] ?? null;

        $parts = [];
        $parts[] = "Sentimen rata-rata {$avg} dengan tren {$trend}, harga {$priceTrend}.";
        $parts[] = "Korelasi same-day " . ($corr === null ? 'n/a' : $corr) . ", lag H+1 " . ($lag1 === null ? 'n/a' : $lag1) . ".";
        $parts[] = "Metode Python terpakai " . ($sentimentStats['python_usage_rate'] * 100) . "%, fallback " . ($sentimentStats['fallback_rate'] * 100) . "%.";
        if (($macroSignal['active'] ?? false) && ($macroSignal['enabled'] ?? false)) {
            $parts[] = (string) ($macroSignal['narrative'] ?? 'Macro regulatory context aktif.');
        }
        $parts[] = "Decision support: {$decision['status']} ({$decision['confidence']}), Prediksi: {$prediction['predicted_direction']} ({$prediction['confidence']}).";

        return implode(' ', $parts);
    }
}
