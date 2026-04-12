<?php

namespace App\Services\Analytics;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Collection;

class SentimentPriceAnalyticsService
{
    public function analyze(Stock $stock, Collection $prices, Collection $articles, int $periodDays = 30): array
    {
        $orderedPrices = $prices->sortBy('price_date')->values();
        $returns = $this->dailyReturns($orderedPrices);
        $perDateSentiment = $this->sentimentByDate($articles, $stock, $periodDays);

        $averageSentiment = round((float) ($articles->avg('sentiment_score') ?? 0), 3);
        $counts = [
            'positive' => $articles->where('sentiment_label', 'positive')->count(),
            'neutral' => $articles->where('sentiment_label', 'neutral')->count(),
            'negative' => $articles->where('sentiment_label', 'negative')->count(),
        ];
        $dominance = $this->dominantSentiment($counts);

        $weightedSentiment = $this->weightedSentiment($articles, $stock, $periodDays);
        $weightedStats = $this->weightedSentimentStats($articles, $stock, $periodDays);
        $newsVolume = $articles->count();
        $dailyReturn = $this->latestReturn($returns);
        $cumulativeReturn = $this->cumulativeReturn($orderedPrices);
        $volatility = $this->volatility($returns);
        $priceTrend = $this->priceTrend($orderedPrices);
        $sentimentTrend = $this->sentimentTrend($perDateSentiment);

        $sameDayCorrelation = $this->sameDayCorrelation($perDateSentiment, $returns);
        $lagCorrelations = [
            'h1' => $this->lagCorrelation($perDateSentiment, $returns, 1),
            'h3' => $this->lagCorrelation($perDateSentiment, $returns, 3),
            'h7' => $this->lagCorrelation($perDateSentiment, $returns, 7),
        ];

        $eventStudy = $this->eventStudy($perDateSentiment, $orderedPrices);
        $volumeImpact = $this->volumeImpact($perDateSentiment, $returns);

        return [
            'average_sentiment' => $averageSentiment,
            'weighted_sentiment' => $weightedSentiment,
            'weighted_sentiment_stats' => $weightedStats,
            'sentiment_dominance' => $dominance,
            'counts' => $counts,
            'news_volume' => $newsVolume,
            'daily_return' => $dailyReturn,
            'cumulative_return' => $cumulativeReturn,
            'volatility' => $volatility,
            'price_trend' => $priceTrend,
            'sentiment_trend' => $sentimentTrend,
            'same_day_correlation' => $sameDayCorrelation,
            'lag_correlations' => $lagCorrelations,
            'event_study' => $eventStudy,
            'volume_impact' => $volumeImpact,
            'per_date_sentiment' => $perDateSentiment,
            'per_date_returns' => $returns,
        ];
    }

    protected function weightedSentiment(Collection $articles, Stock $stock, int $periodDays): float
    {
        $weights = $this->cfg('analytics.source_weights', []);
        $headlineBonus = (float) $this->cfg('analytics.headline_bonus', 0.2);
        $decay = (float) $this->cfg('analytics.recency_decay', 0.4);

        $weightedSum = 0.0;
        $totalWeight = 0.0;

        foreach ($articles as $article) {
            $weight = 1.0;
            $type = $article->source?->type;
            if ($type && isset($weights[$type])) {
                $weight *= (float) $weights[$type];
            }

            if ($this->mentionsStock($article->title, $stock)) {
                $weight += $headlineBonus;
            }

            $daysAgo = optional($article->published_at)->diffInDays(now()) ?? 0;
            $recencyFactor = 1 - (min($daysAgo, $periodDays) / max($periodDays, 1)) * $decay;
            $weight *= max(0.6, $recencyFactor);

            $weightedSum += (float) ($article->sentiment_score ?? 0) * $weight;
            $totalWeight += $weight;
        }

        if ($totalWeight === 0.0) {
            return 0.0;
        }

        return round($weightedSum / $totalWeight, 3);
    }

    protected function mentionsStock(?string $text, Stock $stock): bool
    {
        if (! $text) {
            return false;
        }

        $haystack = mb_strtolower($text);
        $code = mb_strtolower($stock->code);
        $name = mb_strtolower((string) $stock->company_name);

        return str_contains($haystack, $code) || ($name && str_contains($haystack, $name));
    }

    protected function sentimentByDate(Collection $articles, Stock $stock, int $periodDays): Collection
    {
        return $articles
            ->groupBy(fn ($article) => optional($article->published_at)?->toDateString() ?? now()->toDateString())
            ->map(function (Collection $group) use ($stock, $periodDays) {
                $weightedSum = 0.0;
                $totalWeight = 0.0;
                foreach ($group as $article) {
                    $weight = $this->articleWeight($article, $stock, $periodDays);
                    $weightedSum += (float) ($article->sentiment_score ?? 0) * $weight;
                    $totalWeight += $weight;
                }

                return [
                    'avg' => round((float) $group->avg('sentiment_score'), 3),
                    'weighted_avg' => $totalWeight > 0 ? round($weightedSum / $totalWeight, 3) : 0.0,
                    'count' => $group->count(),
                ];
            })
            ->sortKeys();
    }

    protected function articleWeight($article, Stock $stock, int $periodDays): float
    {
        $weights = $this->cfg('analytics.source_weights', []);
        $headlineBonus = (float) $this->cfg('analytics.headline_bonus', 0.2);
        $decay = (float) $this->cfg('analytics.recency_decay', 0.4);

        $weight = 1.0;
        $type = $article->source?->type;
        if ($type && isset($weights[$type])) {
            $weight *= (float) $weights[$type];
        }

        if ($this->mentionsStock($article->title, $stock)) {
            $weight += $headlineBonus;
        }

        $daysAgo = optional($article->published_at)->diffInDays(now()) ?? 0;
        $recencyFactor = 1 - (min($daysAgo, $periodDays) / max($periodDays, 1)) * $decay;
        $weight *= max(0.6, $recencyFactor);

        return $weight;
    }

    protected function weightedSentimentStats(Collection $articles, Stock $stock, int $periodDays): array
    {
        $sum = 0.0;
        $total = 0.0;
        $pos = 0.0;
        $neg = 0.0;
        $neu = 0.0;

        foreach ($articles as $article) {
            $baseWeight = $this->articleWeight($article, $stock, $periodDays);
            $relevance = (float) ($article->relevance_score ?? 1.0);
            $sourceWeight = (float) ($article->source_weight ?? 1.0);
            $effective = $baseWeight * max(0.1, $relevance) * max(0.5, $sourceWeight);

            $score = (float) ($article->sentiment_score ?? 0);
            $label = $article->sentiment_label ?? 'neutral';

            $sum += $score * $effective;
            $total += $effective;

            if ($label === 'positive') {
                $pos += $effective;
            } elseif ($label === 'negative') {
                $neg += $effective;
            } else {
                $neu += $effective;
            }
        }

        $avg = $total > 0 ? round($sum / $total, 3) : 0.0;

        return [
            'weighted_sentiment_score' => $sum,
            'weighted_sentiment_average' => $avg,
            'weighted_positive_count' => round($pos, 3),
            'weighted_negative_count' => round($neg, 3),
            'weighted_neutral_count' => round($neu, 3),
            'total_effective_weight' => round($total, 3),
        ];
    }

    protected function dailyReturns(Collection $prices): array
    {
        $returns = [];
        for ($i = 1; $i < $prices->count(); $i++) {
            $current = $prices[$i];
            $prev = $prices[$i - 1];
            if (! $prev->close) {
                continue;
            }
            $returns[$current->price_date?->toDateString()] = ($current->close - $prev->close) / $prev->close;
        }

        return $returns;
    }

    protected function latestReturn(array $returns): ?float
    {
        if (! count($returns)) {
            return null;
        }

        return round((float) array_values($returns)[count($returns) - 1] * 100, 2);
    }

    protected function cumulativeReturn(Collection $prices): ?float
    {
        if ($prices->count() < 2) {
            return null;
        }

        $first = $prices->first();
        $last = $prices->last();
        if (! $first->close) {
            return null;
        }

        return round((($last->close - $first->close) / $first->close) * 100, 2);
    }

    protected function volatility(array $returns): ?float
    {
        if (count($returns) < 2) {
            return null;
        }

        $values = array_values($returns);
        $avg = array_sum($values) / count($values);
        $variance = array_sum(array_map(fn ($r) => pow($r - $avg, 2), $values)) / count($values);

        return round(sqrt($variance) * 100, 2);
    }

    protected function priceTrend(Collection $prices): string
    {
        if ($prices->count() < 2) {
            return 'datar';
        }

        $first = $prices->first()->close;
        $last = $prices->last()->close;
        if (! $first) {
            return 'datar';
        }

        $returnPct = (($last - $first) / $first) * 100;
        if ($returnPct > 3) {
            return 'naik';
        }

        if ($returnPct < -3) {
            return 'turun';
        }

        return 'datar';
    }

    protected function sentimentTrend(Collection $perDate): string
    {
        if ($perDate->count() < 2) {
            return 'datar';
        }

        $values = $perDate->pluck('avg')->values();
        $first = $values->first();
        $last = $values->last();

        if ($last > $first + 0.1) {
            return 'menguat';
        }
        if ($last < $first - 0.1) {
            return 'melemah';
        }

        return 'datar';
    }

    protected function sameDayCorrelation(Collection $perDateSentiment, array $returns): ?float
    {
        $dates = array_intersect($perDateSentiment->keys()->all(), array_keys($returns));
        if (count($dates) < 3) {
            return null;
        }

        $sentiments = [];
        $rets = [];
        foreach ($dates as $date) {
            $sentiments[] = $perDateSentiment[$date]['avg'] ?? 0;
            $rets[] = $returns[$date] ?? 0;
        }

        return $this->correlation($sentiments, $rets);
    }

    protected function lagCorrelation(Collection $perDateSentiment, array $returns, int $lagDays): ?float
    {
        $sentiments = [];
        $rets = [];
        foreach ($perDateSentiment as $date => $row) {
            $targetDate = Carbon::parse($date)->addDays($lagDays)->toDateString();
            if (isset($returns[$targetDate])) {
                $sentiments[] = $row['avg'] ?? 0;
                $rets[] = $returns[$targetDate];
            }
        }

        if (count($sentiments) < 3) {
            return null;
        }

        return $this->correlation($sentiments, $rets);
    }

    protected function correlation(array $x, array $y): ?float
    {
        $n = min(count($x), count($y));
        if ($n < 3) {
            return null;
        }

        $x = array_slice($x, 0, $n);
        $y = array_slice($y, 0, $n);

        $meanX = array_sum($x) / $n;
        $meanY = array_sum($y) / $n;

        $num = 0;
        $denX = 0;
        $denY = 0;
        for ($i = 0; $i < $n; $i++) {
            $dx = $x[$i] - $meanX;
            $dy = $y[$i] - $meanY;
            $num += $dx * $dy;
            $denX += $dx ** 2;
            $denY += $dy ** 2;
        }

        if ($denX == 0 || $denY == 0) {
            return null;
        }

        return round($num / sqrt($denX * $denY), 2);
    }

    protected function eventStudy(Collection $perDateSentiment, Collection $prices): array
    {
        $threshold = (float) $this->cfg('analytics.event_threshold', 0.35);
        $priceMap = $prices->keyBy(fn ($p) => $p->price_date?->toDateString());

        $positives = [];
        $negatives = [];

        foreach ($perDateSentiment as $date => $row) {
            $sent = $row['avg'] ?? 0;
            $count = $row['count'] ?? 0;
            if ($count < 1) {
                continue;
            }

            if ($sent >= $threshold) {
                $positives[] = [
                    'date' => $date,
                    'sentiment' => $sent,
                    'count' => $count,
                    'impact' => $this->forwardImpact($priceMap, $date),
                ];
            } elseif ($sent <= -$threshold) {
                $negatives[] = [
                    'date' => $date,
                    'sentiment' => $sent,
                    'count' => $count,
                    'impact' => $this->forwardImpact($priceMap, $date),
                ];
            }
        }

        return [
            'positive_events' => $positives,
            'negative_events' => $negatives,
        ];
    }

    protected function forwardImpact(Collection $priceMap, string $date): array
    {
        return [
            'h1' => $this->forwardReturn($priceMap, $date, 1),
            'h3' => $this->forwardReturn($priceMap, $date, 3),
            'h7' => $this->forwardReturn($priceMap, $date, 7),
        ];
    }

    protected function forwardReturn(Collection $priceMap, string $date, int $lagDays): ?float
    {
        $start = $priceMap->first(function ($item, $key) use ($date) {
            return $key >= $date;
        });

        $targetDate = Carbon::parse($date)->addDays($lagDays)->toDateString();
        $target = $priceMap->first(function ($item, $key) use ($targetDate) {
            return $key >= $targetDate;
        });

        if (! $start || ! $target || ! $start->close) {
            return null;
        }

        return round((($target->close - $start->close) / $start->close) * 100, 2);
    }

    protected function volumeImpact(Collection $perDateSentiment, array $returns): array
    {
        $volumes = [];
        $absReturns = [];
        foreach ($perDateSentiment as $date => $row) {
            if (isset($returns[$date])) {
                $volumes[] = $row['count'];
                $absReturns[] = abs($returns[$date]);
            }
        }

        return [
            'correlation' => $this->correlation($volumes, $absReturns),
            'peak_volume_dates' => $perDateSentiment
                ->sortByDesc('count')
                ->take(3)
                ->map(fn ($row, $date) => ['date' => $date, 'count' => $row['count'], 'avg' => $row['avg']])
                ->values()
                ->all(),
        ];
    }

    protected function dominantSentiment(array $counts): string
    {
        arsort($counts);
        return key($counts) ?: 'neutral';
    }

    protected function cfg(string $key, $default = null)
    {
        return function_exists('config') ? config($key, $default) : $default;
    }
}
