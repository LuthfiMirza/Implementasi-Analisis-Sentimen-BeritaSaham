<?php

namespace App\Services\Analytics;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Prediction\FeatureBuilderService;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Http;

class BacktestService
{
    public function __construct(
        protected DecisionSupportService $dss,
        protected ?SentimentPriceAnalyticsService $analyticsService = null,
        protected ?FeatureBuilderService $featureBuilderService = null,
    ) {
        $this->analyticsService ??= new SentimentPriceAnalyticsService();
        $this->featureBuilderService ??= new FeatureBuilderService();
    }

    /**
     * Jalankan backtest untuk satu saham.
     * Sliding window setiap $step hari, prediksi DSS, bandingkan dengan return forward.
     */
    public function runForStock(
        Stock $stock,
        int $lookback = 60,
        int $forward = 5,
        int $step = 5,
        float $threshold = 1.0,
        bool $includeMacroNews = true,
        ?bool $macroRegulatorySignal = null,
        int $maxWindows = 80
    ): array {
        $allPrices = StockPrice::where('stock_id', $stock->id)
            ->where('interval_type', '1d')
            ->orderBy('price_date', 'asc')
            ->get();
        $allPrices = StockPrice::canonicalize($allPrices);

        if ($allPrices->count() < $lookback + $forward) {
            return ['error' => 'Data tidak cukup untuk backtest'];
        }

        $n = $allPrices->count();
        $lastWindowIndex = $n - $forward;
        $firstWindowIndex = $this->firstWindowIndex($lookback, $lastWindowIndex, $step, $maxWindows);

        $firstSignalDate = $this->toCarbon($allPrices[$firstWindowIndex - 1]->price_date);
        $lastSignalDate = $this->toCarbon($allPrices[$lastWindowIndex - 1]->price_date);
        $articleStart = $firstSignalDate->copy()->subDays($lookback + 7)->startOfDay();
        $articleEnd = $lastSignalDate->copy()->endOfDay();

        $allArticles = NewsArticle::forStockContext($stock, $includeMacroNews)
            ->whereNotNull('published_at')
            ->whereBetween('published_at', [$articleStart, $articleEnd])
            ->orderBy('published_at', 'asc')
            ->get();
        $articlesByDate = $allArticles
            ->filter(fn ($article) => $article->published_at !== null)
            ->groupBy(fn ($article) => $article->published_at->toDateString());

        $results = [];
        $regimeResults = [];

        for ($i = $firstWindowIndex; $i <= $lastWindowIndex; $i += $step) {
            $windowPrices = $allPrices->slice($i - $lookback, $lookback)->values();
            $signalDate = $windowPrices->last()->price_date;

            $windowArticles = $this->windowArticlesForDate($articlesByDate, $signalDate, $lookback);

            try {
                $analytics = $this->analyticsService->analyze(
                    $stock,
                    $windowPrices,
                    $windowArticles,
                    $lookback,
                    $signalDate,
                    $macroRegulatorySignal
                );
                $result = $this->dss->analyze($stock, $windowPrices, $windowArticles, $analytics);
                $features = array_merge(
                    $this->featureBuilderService->build($stock, $windowPrices, $windowArticles, $analytics, $lookback, $signalDate),
                    $this->technicalFeaturesForIndex($stock, $allPrices, $i - 1)
                );
            } catch (\Throwable $e) {
                continue;
            }

            $entryPrice = (float) $allPrices[$i]->close;
            $exitPrice = (float) $allPrices[min($i + $forward, $n - 1)]->close;
            $actualReturn = $entryPrice > 0
                ? round(($exitPrice - $entryPrice) / $entryPrice * 100, 2)
                : 0;

            $activeThreshold = $this->effectiveDirectionalThreshold($stock, $features ?? [], $threshold);
            $actualDirection = match (true) {
                $actualReturn > $activeThreshold => 'up',
                $actualReturn < -$activeThreshold => 'down',
                default => 'flat',
            };

            $prediction = $result['prediction'] ?? 'flat';
            $confidence = $result['prediction_confidence'] ?? 0;
            $finalScore = $result['final_score'] ?? 0;
            $modelSource = 'dss_legacy';
            if (isset($features)) {
                $specialPrediction = $this->specialPredictionForBacktest($stock, $features);
                if ($specialPrediction !== null) {
                    $prediction = strtolower((string) ($specialPrediction['predicted_direction'] ?? $prediction));
                    $confidence = (float) ($specialPrediction['probability'] ?? $specialPrediction['confidence'] ?? $confidence);
                    $finalScore = $confidence * 100;
                    $modelSource = (string) ($specialPrediction['model_source'] ?? $specialPrediction['model_variant'] ?? 'special_model');
                }

                $regimePrediction = $this->regimePredictionForBacktest($stock, $features);
                if ($regimePrediction !== null) {
                    $actualRegime = abs($actualReturn) > 0.5 ? 'move' : 'no_move';
                    $predictedRegime = strtolower((string) ($regimePrediction['predicted_regime'] ?? 'no_move'));
                    $regimeResults[] = [
                        'date' => $signalDate?->format('Y-m-d'),
                        'prediction' => $predictedRegime,
                        'actual_regime' => $actualRegime,
                        'actual_return' => $actualReturn,
                        'is_correct' => $predictedRegime === $actualRegime,
                        'confidence' => round((float) ($regimePrediction['probability'] ?? $regimePrediction['confidence'] ?? 0), 3),
                        'model_source' => 'dewa_regime',
                    ];
                }
            }
            $sentimentAvg = $result['sentiment_average'] ?? 0;
            $macroSignal = is_array($result['macro_regulatory_signal'] ?? null)
                ? $result['macro_regulatory_signal']
                : [];

            $results[] = [
                'date' => $signalDate?->format('Y-m-d'),
                'prediction' => $prediction,
                'actual_direction' => $actualDirection,
                'actual_return' => $actualReturn,
                'is_correct' => $prediction === $actualDirection,
                'confidence' => round($confidence, 3),
                'final_score' => round($finalScore, 2),
                'model_source' => $modelSource,
                'active_threshold' => round($activeThreshold, 4),
                'sentiment_avg' => round($sentimentAvg, 4),
                'entry_price' => $entryPrice,
                'exit_price' => $exitPrice,
                'macro_regulatory_attention_score' => round((float) ($macroSignal['context_score'] ?? 0), 3),
                'macro_regulatory_regime' => (string) ($macroSignal['attention_regime'] ?? 'disabled'),
                'macro_regulatory_caution_flag' => (bool) ($macroSignal['caution_flag'] ?? false),
                'macro_regulatory_article_count' => (int) ($macroSignal['article_count'] ?? 0),
            ];
        }

        if (empty($results)) {
            return ['error' => 'Tidak ada hasil backtest'];
        }

        $total = count($results);
        $correct = count(array_filter($results, fn ($r) => $r['is_correct']));
        $accuracy = round($correct / $total * 100, 1);

        $predTypes = ['up', 'flat', 'down'];
        $perPred = [];
        foreach ($predTypes as $pred) {
            $subset = array_filter($results, fn ($r) => $r['prediction'] === $pred);
            $subCorrect = count(array_filter($subset, fn ($r) => $r['is_correct']));
            $perPred[$pred] = [
                'total' => count($subset),
                'correct' => $subCorrect,
                'accuracy' => count($subset) > 0 ? round($subCorrect / count($subset) * 100, 1) : 0,
            ];
        }

        $correctReturns = array_column(array_filter($results, fn ($r) => $r['is_correct']), 'actual_return');
        $wrongReturns = array_column(array_filter($results, fn ($r) => ! $r['is_correct']), 'actual_return');

        $avgReturnCorrect = count($correctReturns) > 0 ? round(array_sum($correctReturns) / count($correctReturns), 2) : 0;
        $avgReturnWrong = count($wrongReturns) > 0 ? round(array_sum($wrongReturns) / count($wrongReturns), 2) : 0;

        $scores = array_column($results, 'final_score');
        $returns = array_column($results, 'actual_return');
        $correlation = $this->pearsonCorrelation($scores, $returns);
        $regulatoryWatchCount = count(array_filter(
            $results,
            fn ($row) => (bool) ($row['macro_regulatory_caution_flag'] ?? false)
        ));
        $averageRegulatoryAttention = count($results) > 0
            ? round(array_sum(array_column($results, 'macro_regulatory_attention_score')) / count($results), 3)
            : 0.0;

        return [
            'stock' => $stock->code,
            'total' => $total,
            'correct' => $correct,
            'accuracy' => $accuracy,
            'per_pred' => $perPred,
            'avg_return_correct' => $avgReturnCorrect,
            'avg_return_wrong' => $avgReturnWrong,
            'correlation' => round($correlation, 3),
            'macro_regulatory_summary' => [
                'signal_enabled' => $macroRegulatorySignal ?? (bool) config('analytics.macro_regulatory_signal.enabled', true),
                'regulatory_watch_count' => $regulatoryWatchCount,
                'average_attention_score' => $averageRegulatoryAttention,
            ],
            'results' => $results,
            'params' => compact('lookback', 'forward', 'step', 'threshold', 'includeMacroNews', 'macroRegulatorySignal', 'maxWindows'),
            'special_models' => $this->summarizeRegimeResults($regimeResults),
        ];
    }

    protected function effectiveDirectionalThreshold(Stock $stock, array $features, float $defaultThreshold): float
    {
        return match ($stock->code) {
            'BUMI' => 2.7,
            'DEWA' => max(0.0, ((float) ($features['atr14_pct'] ?? 0.0)) * 100 * 0.5),
            default => $defaultThreshold,
        };
    }

    protected function technicalFeaturesForIndex(Stock $stock, Collection $prices, int $signalIndex): array
    {
        $slice = $prices->slice(0, $signalIndex + 1)->values();
        $closes = $slice->pluck('close')->map(fn ($value) => (float) $value)->values();
        $highs = $slice->pluck('high')->map(fn ($value) => (float) $value)->values();
        $lows = $slice->pluck('low')->map(fn ($value) => (float) $value)->values();
        $volumes = $slice->pluck('volume')->map(fn ($value) => (float) ($value ?? 0))->values();
        $lastClose = (float) $closes->last();

        return [
            'ticker' => $stock->code,
            'stock' => $stock->code,
            'return_1d' => $this->decimalReturn($closes, 1),
            'return_3d' => $this->decimalReturn($closes, 3),
            'return_5d' => $this->decimalReturn($closes, 5),
            'return_20d' => $this->decimalReturn($closes, 20),
            'atr14_pct' => $this->atrPct($highs, $lows, $closes, 14),
            'atr_ratio' => $this->atrPct($highs, $lows, $closes, 14),
            'volume_ratio_5d' => $this->volumeRatio($volumes, 5, 20),
            'volume_ratio_20d' => $this->volumeRatioCurrent($volumes, 20),
            'price_vs_ema20_pct' => $this->priceVsEma($closes, 20),
            'price_vs_ema50' => $this->priceVsEma($closes, 50),
            'rsi_slope_5d' => $this->rsiSlope($closes, 14, 5),
            'return_5d_cross_section_rank' => 0.5,
            'volume_spike_flag' => $this->volumeSpikeFlag($volumes, 20),
            'market_regime_bullish' => null,
            'regime_duration' => null,
            'last_close' => $lastClose,
        ];
    }

    protected function decimalReturn(Collection $closes, int $lag): ?float
    {
        if ($closes->count() <= $lag) {
            return null;
        }
        $current = (float) $closes->last();
        $previous = (float) $closes[$closes->count() - $lag - 1];
        return $previous > 0 ? round(($current / $previous) - 1, 6) : null;
    }

    protected function atrPct(Collection $highs, Collection $lows, Collection $closes, int $period): ?float
    {
        if ($closes->count() <= $period) {
            return null;
        }
        $ranges = [];
        for ($index = $closes->count() - $period; $index < $closes->count(); $index++) {
            $prevClose = (float) $closes[$index - 1];
            $ranges[] = max(
                (float) $highs[$index] - (float) $lows[$index],
                abs((float) $highs[$index] - $prevClose),
                abs((float) $lows[$index] - $prevClose)
            );
        }
        $lastClose = (float) $closes->last();
        return $lastClose > 0 ? round((array_sum($ranges) / count($ranges)) / $lastClose, 6) : null;
    }

    protected function volumeRatio(Collection $volumes, int $shortWindow, int $longWindow): ?float
    {
        if ($volumes->count() < $longWindow) {
            return null;
        }
        $short = $volumes->take(-$shortWindow)->avg();
        $long = $volumes->take(-$longWindow)->avg();
        return $long > 0 ? round($short / $long, 6) : null;
    }

    protected function volumeRatioCurrent(Collection $volumes, int $window): ?float
    {
        if ($volumes->count() < $window) {
            return null;
        }
        $average = $volumes->take(-$window)->avg();
        return $average > 0 ? round(((float) $volumes->last()) / $average, 6) : null;
    }

    protected function priceVsEma(Collection $closes, int $span): ?float
    {
        if ($closes->count() < $span) {
            return null;
        }
        $multiplier = 2 / ($span + 1);
        $ema = (float) $closes->first();
        foreach ($closes->slice(1) as $close) {
            $ema = (((float) $close - $ema) * $multiplier) + $ema;
        }
        return $ema > 0 ? round(((float) $closes->last() / $ema) - 1, 6) : null;
    }

    protected function rsiSlope(Collection $closes, int $period, int $lag): ?float
    {
        if ($closes->count() <= $period + $lag) {
            return null;
        }
        $current = $this->rsiFromCloses($closes, $period, $closes->count() - 1);
        $previous = $this->rsiFromCloses($closes, $period, $closes->count() - 1 - $lag);
        return $current !== null && $previous !== null ? round($current - $previous, 6) : null;
    }

    protected function rsiFromCloses(Collection $closes, int $period, int $endIndex): ?float
    {
        if ($endIndex < $period) {
            return null;
        }
        $gains = [];
        $losses = [];
        for ($index = $endIndex - $period + 1; $index <= $endIndex; $index++) {
            $change = (float) $closes[$index] - (float) $closes[$index - 1];
            if ($change > 0) {
                $gains[] = $change;
            } elseif ($change < 0) {
                $losses[] = abs($change);
            }
        }
        $avgGain = count($gains) ? array_sum($gains) / count($gains) : 0.0;
        $avgLoss = count($losses) ? array_sum($losses) / count($losses) : 0.0;
        if ($avgLoss == 0.0) {
            return 70.0;
        }
        $rs = $avgGain / $avgLoss;
        return 100 - (100 / (1 + $rs));
    }

    protected function volumeSpikeFlag(Collection $volumes, int $window): ?float
    {
        if ($volumes->count() < $window) {
            return null;
        }
        $average = $volumes->take(-$window)->avg();
        return (float) $volumes->last() > ($average * 2) ? 1.0 : 0.0;
    }

    protected function specialPredictionForBacktest(Stock $stock, array $features): ?array
    {
        $variant = match ($stock->code) {
            'BUMI' => 'bumi_technical',
            'DEWA' => 'dewa_technical',
            default => null,
        };

        return $variant ? $this->postPrediction($features, $variant) : null;
    }

    protected function regimePredictionForBacktest(Stock $stock, array $features): ?array
    {
        return $stock->code === 'DEWA' ? $this->postPrediction($features, 'dewa_regime') : null;
    }

    protected function postPrediction(array $features, string $variant): ?array
    {
        $endpoint = (string) config('services.python_prediction.endpoint');
        if ($endpoint === '') {
            return null;
        }

        try {
            $response = Http::timeout((int) config('services.python_prediction.timeout', 5))
                ->post($endpoint, ['features' => $features, 'model_variant' => $variant]);

            return $response->successful() && is_array($response->json()) ? $response->json() : null;
        } catch (\Throwable) {
            return null;
        }
    }

    protected function summarizeRegimeResults(array $rows): array
    {
        if (empty($rows)) {
            return [];
        }

        $total = count($rows);
        $correct = count(array_filter($rows, fn ($row) => (bool) $row['is_correct']));

        return [
            'dewa_regime' => [
                'label_type' => 'move_vs_no_move',
                'total' => $total,
                'correct' => $correct,
                'accuracy' => round($correct / $total * 100, 1),
                'results' => $rows,
            ],
        ];
    }

    public function runAll(
        int $lookback = 60,
        int $forward = 5,
        int $step = 5,
        float $threshold = 1.0,
        bool $includeMacroNews = true,
        ?bool $macroRegulatorySignal = null,
        int $maxWindows = 40
    ): array {
        $stocks = Stock::where('is_active', true)->get();
        $allResults = [];
        $summary = [
            'total_predictions' => 0,
            'total_correct' => 0,
            'per_stock' => [],
        ];

        foreach ($stocks as $stock) {
            $result = $this->runForStock(
                $stock,
                $lookback,
                $forward,
                $step,
                $threshold,
                $includeMacroNews,
                $macroRegulatorySignal,
                $maxWindows
            );
            if (isset($result['error'])) {
                continue;
            }

            $allResults[$stock->code] = $result;
            $summary['total_predictions'] += $result['total'];
            $summary['total_correct'] += $result['correct'];
            $summary['per_stock'][] = [
                'code' => $stock->code,
                'total' => $result['total'],
                'accuracy' => $result['accuracy'],
                'correlation' => $result['correlation'],
            ];
        }

        $total = $summary['total_predictions'];
        $summary['overall_accuracy'] = $total > 0 ? round($summary['total_correct'] / $total * 100, 1) : 0;

        return compact('summary', 'allResults');
    }

    protected function firstWindowIndex(int $lookback, int $lastWindowIndex, int $step, int $maxWindows): int
    {
        if ($maxWindows <= 0) {
            return $lookback;
        }

        return max($lookback, $lastWindowIndex - (($maxWindows - 1) * $step));
    }

    protected function windowArticlesForDate(Collection $articlesByDate, CarbonInterface|string $signalDate, int $lookback, int $limit = 50): Collection
    {
        $signal = $this->toCarbon($signalDate)->endOfDay();
        $start = $signal->copy()->subDays($lookback)->startOfDay();
        $dates = [];

        for ($cursor = $start->copy(); $cursor->lte($signal); $cursor->addDay()) {
            $dates[] = $cursor->toDateString();
        }

        return collect($dates)
            ->flatMap(fn (string $date) => $articlesByDate->get($date, collect()))
            ->sortByDesc('published_at')
            ->take($limit)
            ->sortBy('published_at')
            ->values();
    }

    protected function toCarbon(CarbonInterface|string $value): Carbon
    {
        return $value instanceof CarbonInterface ? Carbon::parse($value) : Carbon::parse($value);
    }

    protected function pearsonCorrelation(array $x, array $y): float
    {
        $n = count($x);
        if ($n < 2) {
            return 0;
        }

        $meanX = array_sum($x) / $n;
        $meanY = array_sum($y) / $n;

        $num = 0;
        $denX = 0;
        $denY = 0;
        for ($i = 0; $i < $n; $i++) {
            $dx = $x[$i] - $meanX;
            $dy = $y[$i] - $meanY;
            $num += $dx * $dy;
            $denX += $dx * $dx;
            $denY += $dy * $dy;
        }

        $den = sqrt($denX * $denY);
        return $den > 0 ? $num / $den : 0;
    }
}
