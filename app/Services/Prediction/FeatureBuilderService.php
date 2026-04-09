<?php

namespace App\Services\Prediction;

use App\Models\Stock;
use Illuminate\Support\Collection;

class FeatureBuilderService
{
    public function build(
        Stock $stock,
        Collection $prices,
        Collection $articles,
        array $analytics,
        int $periodDays = 30
    ): array {
        $orderedPrices = $prices->sortBy('price_date')->values();
        $ma5 = $this->movingAverage($orderedPrices, 5);
        $ma20 = $this->movingAverage($orderedPrices, 20);

        return [
            'stock' => $stock->code,
            'period' => $periodDays,
            'sentiment_average' => $analytics['average_sentiment'] ?? 0,
            'weighted_sentiment' => $analytics['weighted_sentiment'] ?? 0,
            'sentiment_dominance' => $analytics['sentiment_dominance'] ?? 'neutral',
            'news_volume' => $analytics['news_volume'] ?? 0,
            'positive_news_count' => $analytics['counts']['positive'] ?? 0,
            'negative_news_count' => $analytics['counts']['negative'] ?? 0,
            'daily_return_lag1' => $this->lagReturn($orderedPrices, 1),
            'daily_return_lag3' => $this->lagReturn($orderedPrices, 3),
            'daily_return_lag7' => $this->lagReturn($orderedPrices, 7),
            'moving_average_5' => $ma5,
            'moving_average_20' => $ma20,
            'ma_gap' => $this->maGap($ma5, $ma20),
            'volatility' => $analytics['volatility'] ?? null,
            'rsi' => $this->rsi($orderedPrices),
            'headline_count' => $this->headlineCount($articles, $stock),
            'last_close' => $orderedPrices->last()->close ?? null,
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
        $ordered = $prices->values();

        for ($i = 1; $i <= $period; $i++) {
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
}
