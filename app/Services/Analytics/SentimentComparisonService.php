<?php

namespace App\Services\Analytics;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use App\Services\Prediction\FeatureBuilderService;
use App\Services\Prediction\PredictionEngineManager;
use App\Services\Stocks\PriceSeriesService;
use Carbon\Carbon;
use Illuminate\Support\Collection;

class SentimentComparisonService
{
    public function __construct(
        protected PriceSeriesService $priceSeriesService,
        protected SentimentPriceAnalyticsService $analyticsService,
        protected FeatureBuilderService $featureBuilderService,
        protected PredictionEngineManager $predictionEngineManager
    ) {
    }

    public function evaluate(Stock $stock, int $period = 30): array
    {
        $period = max(7, $period);
        $prices = $this->priceSeriesService->getSeries($stock, '1d', $period + 7)->values();

        $articles = NewsArticle::where('stock_id', $stock->id)
            ->whereNotNull('published_at')
            ->where('published_at', '>=', now()->subDays($period))
            ->orderBy('published_at')
            ->get();

        $analytics = $this->analyticsService->analyze($stock, $prices, $articles, $period);

        $perDate = $analytics['per_date_sentiment'] ?? collect();
        $perDate = $perDate instanceof Collection ? $perDate : collect($perDate);
        $perDateReturns = $analytics['per_date_returns'] ?? [];

        $corr = $this->compareCorrelations($perDate, $perDateReturns);
        $events = $this->compareEvents($perDate, $prices);
        $signals = $this->compareSignals($perDate, $prices);

        // Prediction impact comparison (Mode A vs Mode B)
        $predictionImpact = $this->predictionImpact($stock, $prices, $articles, $analytics, $period);

        return [
            'stock' => $stock->code,
            'period_days' => $period,
            'data_points' => [
                'price_points' => $prices->count(),
                'article_count' => $articles->count(),
                'days_with_sentiment' => $perDate->count(),
            ],
            'correlation' => $corr,
            'event_study' => $events,
            'signal_backtest' => $signals,
            'prediction_impact' => $predictionImpact,
            'narrative' => $this->narrative($corr, $events, $signals),
        ];
    }

    protected function compareCorrelations(Collection $perDate, array $perDateReturns): array
    {
        $avgSeries = [];
        $weightedSeries = [];
        foreach ($perDate as $date => $row) {
            $avgSeries[$date] = $row['avg'] ?? 0;
            $weightedSeries[$date] = $row['weighted_avg'] ?? 0;
        }

        return [
            'same_day' => [
                'average' => $this->correlationAligned($avgSeries, $perDateReturns),
                'weighted' => $this->correlationAligned($weightedSeries, $perDateReturns),
            ],
            'lag' => [
                'h1' => [
                    'average' => $this->lagCorrelation($avgSeries, $perDateReturns, 1),
                    'weighted' => $this->lagCorrelation($weightedSeries, $perDateReturns, 1),
                ],
                'h3' => [
                    'average' => $this->lagCorrelation($avgSeries, $perDateReturns, 3),
                    'weighted' => $this->lagCorrelation($weightedSeries, $perDateReturns, 3),
                ],
                'h7' => [
                    'average' => $this->lagCorrelation($avgSeries, $perDateReturns, 7),
                    'weighted' => $this->lagCorrelation($weightedSeries, $perDateReturns, 7),
                ],
            ],
        ];
    }

    protected function predictionImpact(Stock $stock, Collection $prices, Collection $articles, array $analytics, int $period): array
    {
        $returns = $this->dailyReturns($prices->sortBy('price_date')->values());
        $directionMap = $this->directionMap($returns, 1); // H+1 label

        // Mode A: tanpa weighted_sentiment_quality
        $featuresA = $this->featureBuilderService->build($stock, $prices, $articles, $analytics, $period);
        unset($featuresA['weighted_sentiment_quality']);
        $predA = $this->predictionEngineManager->predict($featuresA);

        // Mode B: dengan weighted_sentiment_quality (default)
        $featuresB = $this->featureBuilderService->build($stock, $prices, $articles, $analytics, $period);
        $predB = $this->predictionEngineManager->predict($featuresB);

        $label = $directionMap['label'] ?? null;

        return [
            'mode_a' => [
                'prediction' => $predA,
                'label_h1' => $label,
                'is_correct' => $this->isDirectionCorrect($predA['predicted_direction'] ?? null, $label),
            ],
            'mode_b' => [
                'prediction' => $predB,
                'label_h1' => $label,
                'is_correct' => $this->isDirectionCorrect($predB['predicted_direction'] ?? null, $label),
            ],
            'note' => 'Evaluasi heuristik: label diambil dari return H+1 terakhir yang tersedia.',
        ];
    }

    protected function dailyReturns(Collection $prices): array
    {
        $ordered = $prices->sortBy('price_date')->values();
        $returns = [];
        for ($i = 1; $i < $ordered->count(); $i++) {
            $current = $ordered[$i];
            $prev = $ordered[$i - 1];
            if (! $prev->close) {
                continue;
            }
            $returns[$current->price_date?->toDateString()] = ($current->close - $prev->close) / $prev->close;
        }
        return $returns;
    }

    protected function directionMap(array $returns, int $lag): array
    {
        if (count($returns) < $lag + 1) {
            return [];
        }
        $keys = array_keys($returns);
        $targetDate = $keys[count($keys) - 1];
        $ret = $returns[$targetDate] ?? null;
        if ($ret === null) {
            return [];
        }
        $label = 'flat';
        if ($ret > 0.001) {
            $label = 'up';
        } elseif ($ret < -0.001) {
            $label = 'down';
        }
        return ['date' => $targetDate, 'return' => $ret, 'label' => $label];
    }

    protected function isDirectionCorrect(?string $pred, ?string $label): ?bool
    {
        if (! $pred || ! $label) {
            return null;
        }
        if ($pred === 'flat' && $label === 'flat') {
            return true;
        }
        if ($pred === 'up' && $label === 'up') {
            return true;
        }
        if ($pred === 'down' && $label === 'down') {
            return true;
        }
        return false;
    }

    protected function compareEvents(Collection $perDate, Collection $prices): array
    {
        $threshold = 0.4;
        $priceMap = $prices->keyBy(fn ($p) => $p->price_date?->toDateString());

        $eventsAvg = $this->detectEvents($perDate, $priceMap, $threshold, 'avg');
        $eventsW = $this->detectEvents($perDate, $priceMap, $threshold, 'weighted_avg');

        return [
            'average' => $eventsAvg,
            'weighted' => $eventsW,
        ];
    }

    protected function compareSignals(Collection $perDate, Collection $prices): array
    {
        $threshold = 0.15;
        $priceMap = $prices->keyBy(fn ($p) => $p->price_date?->toDateString());

        $signalsAvg = $this->evaluateSignalsMultiHorizon($perDate, $priceMap, $threshold, 'avg');
        $signalsW = $this->evaluateSignalsMultiHorizon($perDate, $priceMap, $threshold, 'weighted_avg');

        return [
            'average' => $signalsAvg,
            'weighted' => $signalsW,
        ];
    }

    protected function correlationAligned(array $sentiments, array $returns): ?float
    {
        $dates = array_intersect(array_keys($sentiments), array_keys($returns));
        if (count($dates) < 3) {
            return null;
        }
        $x = [];
        $y = [];
        foreach ($dates as $d) {
            $x[] = $sentiments[$d] ?? 0;
            $y[] = $returns[$d] ?? 0;
        }
        return $this->correlation($x, $y);
    }

    protected function lagCorrelation(array $sentiments, array $returns, int $lag): ?float
    {
        $x = [];
        $y = [];
        foreach ($sentiments as $date => $s) {
            $target = Carbon::parse($date)->addDays($lag)->toDateString();
            if (isset($returns[$target])) {
                $x[] = $s;
                $y[] = $returns[$target];
            }
        }
        if (count($x) < 3) {
            return null;
        }
        return $this->correlation($x, $y);
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
        $num = 0; $denX = 0; $denY = 0;
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
        return round($num / sqrt($denX * $denY), 3);
    }

    protected function detectEvents(Collection $perDate, Collection $priceMap, float $threshold, string $key): array
    {
        $events = [];
        foreach ($perDate as $date => $row) {
            $val = $row[$key] ?? null;
            $count = $row['count'] ?? 0;
            if ($val === null || $count < 1) {
                continue;
            }
            if (abs($val) >= $threshold) {
                $events[] = [
                    'date' => $date,
                    'sentiment' => $val,
                    'count' => $count,
                    'impact' => [
                        'h1' => $this->forwardReturn($priceMap, $date, 1),
                        'h3' => $this->forwardReturn($priceMap, $date, 3),
                        'h7' => $this->forwardReturn($priceMap, $date, 7),
                    ],
                ];
            }
        }
        return $events;
    }

    protected function evaluateSignalsMultiHorizon(Collection $perDate, Collection $priceMap, float $threshold, string $key): array
    {
        $horizons = [1, 3, 7];
        $stats = [];
        $counts = ['bullish' => 0, 'neutral' => 0, 'bearish' => 0];

        foreach ($horizons as $h) {
            $stats["h{$h}"] = [
                'directional_accuracy' => null,
                'bullish_hit_rate' => null,
                'bearish_hit_rate' => null,
                'neutral_hit_rate' => null,
                'avg_return_after_bullish' => null,
                'avg_return_after_bearish' => null,
                'avg_return_after_neutral' => null,
            ];
        }

        $records = [];

        foreach ($perDate as $date => $row) {
            $val = $row[$key] ?? null;
            if ($val === null) {
                continue;
            }
            $signal = 'neutral';
            if ($val >= $threshold) {
                $signal = 'bullish';
            } elseif ($val <= -$threshold) {
                $signal = 'bearish';
            }
            $counts[$signal]++;

            $record = ['signal' => $signal, 'returns' => []];
            foreach ($horizons as $h) {
                $record['returns']["h{$h}"] = $this->forwardReturn($priceMap, $date, $h);
            }
            $records[] = $record;
        }

        foreach ($horizons as $h) {
            $hit = 0;
            $total = 0;
            $bullHit = $bearHit = $neuHit = 0;
            $bullCount = $bearCount = $neuCount = 0;
            $bullRet = $bearRet = $neuRet = [];

            foreach ($records as $rec) {
                $ret = $rec['returns']["h{$h}"];
                if ($ret === null) {
                    continue;
                }
                $total++;
                $signal = $rec['signal'];
                if ($signal === 'bullish') {
                    $bullCount++;
                    if ($ret > 0) {
                        $hit++;
                        $bullHit++;
                    }
                    $bullRet[] = $ret;
                } elseif ($signal === 'bearish') {
                    $bearCount++;
                    if ($ret < 0) {
                        $hit++;
                        $bearHit++;
                    }
                    $bearRet[] = $ret;
                } else {
                    $neuCount++;
                    if (abs($ret) < 0.1) {
                        $hit++;
                        $neuHit++;
                    }
                    $neuRet[] = $ret;
                }
            }

            $stats["h{$h}"] = [
                'directional_accuracy' => $total > 0 ? round($hit / $total, 3) : null,
                'bullish_hit_rate' => $bullCount > 0 ? round($bullHit / $bullCount, 3) : null,
                'bearish_hit_rate' => $bearCount > 0 ? round($bearHit / $bearCount, 3) : null,
                'neutral_hit_rate' => $neuCount > 0 ? round($neuHit / $neuCount, 3) : null,
                'avg_return_after_bullish' => $this->avg($bullRet),
                'avg_return_after_bearish' => $this->avg($bearRet),
                'avg_return_after_neutral' => $this->avg($neuRet),
                'signal_count' => [
                    'bullish' => $bullCount,
                    'bearish' => $bearCount,
                    'neutral' => $neuCount,
                ],
            ];
        }

        return $stats;
    }

    protected function forwardReturn(Collection $priceMap, string $date, int $lag): ?float
    {
        $start = $priceMap->get($date);
        $targetDate = Carbon::parse($date)->addDays($lag)->toDateString();
        $target = $priceMap->first(function ($item, $key) use ($targetDate) {
            return $key >= $targetDate;
        });

        if (! $start || ! $target || ! $start->close) {
            return null;
        }

        return round((($target->close - $start->close) / $start->close) * 100, 2);
    }

    protected function avg(array $arr): ?float
    {
        if (! count($arr)) {
            return null;
        }
        return round(array_sum($arr) / count($arr), 3);
    }

    protected function narrative(array $corr, array $events, array $signals): string
    {
        $sameDayWeighted = $corr['same_day']['weighted'] ?? null;
        $sameDayAvg = $corr['same_day']['average'] ?? null;

        $parts = [];
        if ($sameDayWeighted !== null && $sameDayAvg !== null) {
            $parts[] = "Korelasi same-day weighted: {$sameDayWeighted}, average: {$sameDayAvg}.";
        }

        $evW = count($events['weighted'] ?? []);
        $evA = count($events['average'] ?? []);
        $parts[] = "Event weighted: {$evW}, event average: {$evA}.";

        $parts[] = "Hit rate sinyal bullish (weighted/avg): ".($signals['weighted']['bullish_hit_rate_h1'] ?? 'n/a')."/".($signals['average']['bullish_hit_rate_h1'] ?? 'n/a').".";

        return implode(' ', $parts);
    }
}
