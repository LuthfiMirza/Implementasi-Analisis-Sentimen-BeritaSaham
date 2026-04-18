<?php

namespace App\Services\Prediction;

use App\Models\Stock;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;

class FeatureBuilderService
{
    public function build(
        Stock $stock,
        Collection $prices,
        Collection $articles,
        array $analytics,
        int $periodDays = 30,
        CarbonInterface|string|null $referenceDate = null
    ): array {
        $orderedPrices = $prices->sortBy('price_date')->values();
        $referencePoint = $this->resolveReferenceDate($referenceDate, $orderedPrices);
        $ma5 = $this->movingAverage($orderedPrices, 5);
        $ma20 = $this->movingAverage($orderedPrices, 20);

        $articlesInPeriod = $this->articlesInPeriod($articles, $periodDays, $referencePoint);

        $sentimentMap = ['positive' => 1, 'neutral' => 0, 'negative' => -1];
        $scores = $articlesInPeriod->map(function ($a) use ($sentimentMap) {
            return $sentimentMap[$a->sentiment_label] ?? 0;
        });
        $sentimentAverage = $scores->count() > 0 ? round($scores->avg(), 4) : 0;

        $weightedScores = $articlesInPeriod->map(function ($a) use ($sentimentMap) {
            if (! is_null($a->sentiment_score)) {
                return (float) $a->sentiment_score;
            }
            return $sentimentMap[$a->sentiment_label] ?? 0;
        });
        $weightedSentiment = $weightedScores->count() > 0 ? round($weightedScores->avg(), 4) : 0;

        $newsVolume = $articlesInPeriod->count();
        $macroSignal = is_array($analytics['macro_regulatory_signal'] ?? null)
            ? $analytics['macro_regulatory_signal']
            : [];

        // Volatility (std dev of daily returns)
        $closes = $orderedPrices->pluck('close')->map(fn ($v) => (float) $v)->values()->all();
        $returns = [];
        for ($i = 1; $i < count($closes); $i++) {
            if ($closes[$i - 1] > 0) {
                $returns[] = ($closes[$i] - $closes[$i - 1]) / $closes[$i - 1] * 100;
            }
        }
        $volatility = null;
        if (count($returns) > 1) {
            $mean = array_sum($returns) / count($returns);
            $variance = array_sum(array_map(fn ($r) => pow($r - $mean, 2), $returns)) / (count($returns) - 1);
            $volatility = round(sqrt($variance), 4);
        }

        return [
            'stock' => $stock->code,
            'period' => $periodDays,
            'sentiment_average' => $sentimentAverage,
            'weighted_sentiment' => $weightedSentiment,
            'weighted_sentiment_quality' => data_get($analytics, 'weighted_sentiment_stats.weighted_sentiment_average', $weightedSentiment),
            'sentiment_dominance' => $analytics['sentiment_dominance'] ?? 'neutral',
            'news_volume' => $newsVolume,
            'positive_news_count' => $articlesInPeriod->where('sentiment_label', 'positive')->count(),
            'neutral_news_count' => $articlesInPeriod->where('sentiment_label', 'neutral')->count(),
            'negative_news_count' => $articlesInPeriod->where('sentiment_label', 'negative')->count(),
            'macro_regulatory_signal_enabled' => (bool) ($macroSignal['enabled'] ?? false),
            'macro_regulatory_signal_active' => (bool) ($macroSignal['active'] ?? false),
            'macro_regulatory_attention_score' => (float) ($macroSignal['context_score'] ?? 0.0),
            'macro_regulatory_article_count' => (int) ($macroSignal['article_count'] ?? 0),
            'macro_regulatory_neutral_share' => (float) ($macroSignal['neutral_share'] ?? 0.0),
            'macro_regulatory_caution_flag' => (bool) ($macroSignal['caution_flag'] ?? false),
            'macro_regulatory_confidence_multiplier' => (float) ($macroSignal['confidence_multiplier'] ?? 1.0),
            'macro_regulatory_score_multiplier' => (float) ($macroSignal['score_multiplier'] ?? 1.0),
            'macro_regulatory_threshold_tightening_factor' => (float) ($macroSignal['threshold_tightening_factor'] ?? 1.0),
            'macro_regulatory_attention_regime' => (string) ($macroSignal['attention_regime'] ?? 'normal'),
            'daily_return_lag1' => $this->lagReturn($orderedPrices, 1),
            'daily_return_lag3' => $this->lagReturn($orderedPrices, 3),
            'daily_return_lag7' => $this->lagReturn($orderedPrices, 7),
            'moving_average_5' => $ma5,
            'moving_average_20' => $ma20,
            'ma_gap' => $this->maGap($ma5, $ma20),
            'volatility' => $volatility,
            'rsi' => $this->rsi($orderedPrices),
            'headline_count' => $this->headlineCount($articlesInPeriod, $stock),
            'last_close' => $orderedPrices->last()->close ?? null,
            'price_trend' => $analytics['price_trend'] ?? 'datar',
            'cumulative_return' => $analytics['cumulative_return'] ?? null,
            'same_day_correlation' => $analytics['same_day_correlation'] ?? null,
            'lag_correlation_h1' => data_get($analytics, 'lag_correlations.h1'),
            'lag_correlation_h3' => data_get($analytics, 'lag_correlations.h3'),
            'lag_correlation_h7' => data_get($analytics, 'lag_correlations.h7'),
            'reference_date' => $referencePoint?->toDateString(),
        ];
    }

    protected function movingAverage(Collection $prices, int $window): ?float
    {
        if ($prices->count() < $window) {
            return null;
        }

        return round($prices->take(-$window)->avg('close'), 2);
    }

    protected function maGap(?float $ma5, ?float $ma20): ?float
    {
        if ($ma5 === null || $ma20 === null || $ma20 == 0.0) {
            return null;
        }

        return round(($ma5 - $ma20) / $ma20, 4);
    }

    protected function lagReturn(Collection $prices, int $lag): ?float
    {
        if ($prices->count() <= $lag) {
            return null;
        }

        $last = $prices->last();
        $previous = $prices[$prices->count() - ($lag + 1)];
        if (! $previous->close) {
            return null;
        }

        return round((($last->close - $previous->close) / $previous->close) * 100, 2);
    }

    protected function rsi(Collection $prices, int $period = 14): ?float
    {
        if ($prices->count() <= $period) {
            return null;
        }

        $gains = [];
        $losses = [];
        $ordered = $prices->take(-($period + 1))->values();

        for ($i = 1; $i < $ordered->count(); $i++) {
            $change = ($ordered[$i]->close - $ordered[$i - 1]->close);
            if ($change > 0) {
                $gains[] = $change;
            } else {
                $losses[] = abs($change);
            }
        }

        $avgGain = array_sum($gains) / max(count($gains), 1);
        $avgLoss = array_sum($losses) / max(count($losses), 1);

        if ($avgLoss == 0.0) {
            return 70;
        }

        $rs = $avgGain / $avgLoss;
        $rsi = 100 - (100 / (1 + $rs));

        return round($rsi, 2);
    }

    protected function headlineCount(Collection $articles, Stock $stock): int
    {
        $code = mb_strtolower($stock->code);
        $name = mb_strtolower((string) $stock->company_name);

        return $articles->filter(function ($article) use ($code, $name) {
            $title = mb_strtolower((string) $article->title);
            return str_contains($title, $code) || ($name && str_contains($title, $name));
        })->count();
    }

    protected function resolveReferenceDate(CarbonInterface|string|null $referenceDate, Collection $prices): CarbonInterface
    {
        if ($referenceDate instanceof CarbonInterface) {
            return $referenceDate;
        }

        if (is_string($referenceDate) && trim($referenceDate) !== '') {
            return Carbon::parse($referenceDate);
        }

        $lastPriceDate = $prices->last()?->price_date;
        if ($lastPriceDate instanceof CarbonInterface) {
            return $lastPriceDate;
        }

        if ($lastPriceDate) {
            return Carbon::parse($lastPriceDate);
        }

        return now();
    }

    protected function articlesInPeriod(Collection $articles, int $periodDays, CarbonInterface $referencePoint): Collection
    {
        $periodStart = $referencePoint->copy()->subDays(max(1, $periodDays));
        $qualityThreshold = (float) config('news.final_quality_threshold', 0.4);

        return $articles
            ->filter(function ($article) use ($periodStart, $referencePoint, $qualityThreshold) {
                if (! $article->published_at) {
                    return false;
                }

                if ($article->final_quality_score !== null && (float) $article->final_quality_score < $qualityThreshold) {
                    return false;
                }

                $published = $article->published_at instanceof CarbonInterface
                    ? $article->published_at->copy()
                    : Carbon::parse($article->published_at);

                return $published->greaterThanOrEqualTo($periodStart)
                    && $published->lessThanOrEqualTo($referencePoint);
            })
            ->sortBy('published_at')
            ->values();
    }
}
