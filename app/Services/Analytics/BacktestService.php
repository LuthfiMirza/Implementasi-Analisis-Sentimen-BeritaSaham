<?php

namespace App\Services\Analytics;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;

class BacktestService
{
    public function __construct(
        protected DecisionSupportService $dss,
        protected ?SentimentPriceAnalyticsService $analyticsService = null,
    ) {
        $this->analyticsService ??= new SentimentPriceAnalyticsService();
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
            } catch (\Throwable $e) {
                continue;
            }

            $entryPrice = (float) $allPrices[$i]->close;
            $exitPrice = (float) $allPrices[min($i + $forward, $n - 1)]->close;
            $actualReturn = $entryPrice > 0
                ? round(($exitPrice - $entryPrice) / $entryPrice * 100, 2)
                : 0;

            $actualDirection = match (true) {
                $actualReturn > $threshold => 'up',
                $actualReturn < -$threshold => 'down',
                default => 'flat',
            };

            $prediction = $result['prediction'] ?? 'flat';
            $confidence = $result['prediction_confidence'] ?? 0;
            $finalScore = $result['final_score'] ?? 0;
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
