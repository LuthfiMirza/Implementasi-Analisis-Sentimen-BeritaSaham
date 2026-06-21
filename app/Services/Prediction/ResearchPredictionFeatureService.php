<?php

namespace App\Services\Prediction;

use App\Models\Stock;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;

class ResearchPredictionFeatureService
{
    public const FEATURE_COLUMNS = [
        'return_1d',
        'return_3d',
        'return_5d',
        'return_20d',
        'atr_ratio',
        'atr14_pct',
        'volume_ratio_5d',
        'volume_ratio_20d',
        'price_vs_ema20_pct',
        'price_vs_ema50',
        'rsi_slope_5d',
        'return_5d_cross_section_rank',
        'volume_spike_flag',
        'market_regime_bullish',
        'regime_duration',
        'has_sentiment_data',
        'sentiment_average_5d',
        'weighted_sentiment_5d',
        'news_volume_5d',
        'sentiment_average_5d_x_regime',
        'weighted_sentiment_5d_x_regime',
    ];

    protected array $stockSeriesCache = [];

    protected ?Collection $ihsgRegimeCache = null;

    protected ?Collection $ihsgRegimeStateCache = null;

    public function __construct(
        protected ?string $stockDataDir = null,
        protected ?string $ihsgCsvPath = null,
    ) {
        $this->stockDataDir ??= base_path('data/stocks');
        $this->ihsgCsvPath ??= base_path('data/IHSG.csv');
    }

    public function buildForDate(
        Stock $stock,
        Collection $articles,
        CarbonInterface|string|null $referenceDate,
        int $sentimentLookbackDays = 5,
    ): array {
        $referencePoint = $this->resolveReferenceDate($referenceDate);
        $stockSeries = $this->seriesForStock($stock);
        $row = $stockSeries->get($referencePoint->toDateString());

        $regimeState = $this->ihsgRegimeStateMap()->get($referencePoint->toDateString());
        $regimeBullish = $regimeState['bullish'] ?? null;
        $regimeSign = $regimeBullish === null ? 0 : ($regimeBullish ? 1 : -1);
        $sentimentStats = $this->sentimentWindowStats($stock, $articles, $referencePoint, $sentimentLookbackDays);

        return [
            'prediction_feature_version' => 'technical_prediction_research_v2',
            'prediction_target_horizon_days' => 5,
            'prediction_label_threshold' => 0.015,
            'return_1d' => $row['return_1d'] ?? null,
            'return_3d' => $row['return_3d'] ?? null,
            'return_5d' => $row['return_5d'] ?? null,
            'return_20d' => $row['return_20d'] ?? null,
            'atr_ratio' => $row['atr_ratio'] ?? null,
            'atr14_pct' => $row['atr14_pct'] ?? null,
            'volume_ratio_5d' => $row['volume_ratio_5d'] ?? null,
            'volume_ratio_20d' => $row['volume_ratio_20d'] ?? null,
            'price_vs_ema20_pct' => $row['price_vs_ema20_pct'] ?? null,
            'price_vs_ema50' => $row['price_vs_ema50'] ?? null,
            'rsi_slope_5d' => $row['rsi_slope_5d'] ?? null,
            'return_5d_cross_section_rank' => $row['return_5d_cross_section_rank'] ?? null,
            'volume_spike_flag' => $row['volume_spike_flag'] ?? null,
            'market_regime_bullish' => $regimeBullish === null ? null : (int) $regimeBullish,
            'regime_duration' => $regimeState['duration'] ?? null,
            'has_sentiment_data' => $sentimentStats['has_sentiment_data'],
            'sentiment_average_5d' => $sentimentStats['sentiment_average_5d'],
            'weighted_sentiment_5d' => $sentimentStats['weighted_sentiment_5d'],
            'news_volume_5d' => $sentimentStats['news_volume_5d'],
            'sentiment_available_count_5d' => $sentimentStats['sentiment_available_count_5d'],
            'sentiment_unavailable_count_5d' => $sentimentStats['sentiment_unavailable_count_5d'],
            'sentiment_average_5d_x_regime' => $regimeSign === 0 ? 0.0 : round($sentimentStats['sentiment_average_5d'] * $regimeSign, 6),
            'weighted_sentiment_5d_x_regime' => $regimeSign === 0 ? 0.0 : round($sentimentStats['weighted_sentiment_5d'] * $regimeSign, 6),
            'adjusted_price_basis' => 'back_adjusted_ohlc_via_adj_close_factor',
            'reference_date' => $referencePoint->toDateString(),
        ];
    }

    public function seriesForStock(Stock $stock): Collection
    {
        if (isset($this->stockSeriesCache[$stock->code])) {
            return $this->stockSeriesCache[$stock->code];
        }

        $path = rtrim($this->stockDataDir, DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR.$stock->code.'.csv';
        if (! is_file($path)) {
            return $this->stockSeriesCache[$stock->code] = collect();
        }

        $rows = $this->readCsv($path)
            ->map(function (array $row): array {
                $close = $this->floatOrNull($row['close'] ?? null);
                $adjClose = $this->floatOrNull($row['adj_close'] ?? null);
                $factor = ($close && $adjClose) ? ($adjClose / $close) : 1.0;

                return [
                    'date' => (string) ($row['date'] ?? ''),
                    'open_adj' => $this->scaledValue($row['open'] ?? null, $factor),
                    'high_adj' => $this->scaledValue($row['high'] ?? null, $factor),
                    'low_adj' => $this->scaledValue($row['low'] ?? null, $factor),
                    'close_adj' => $adjClose ?? $close,
                    'volume' => (int) round((float) ($row['volume'] ?? 0)),
                ];
            })
            ->filter(fn (array $row): bool => ($row['date'] ?? '') !== '' && $row['close_adj'] !== null)
            ->values();

        $ema20 = null;
        $ema50 = null;
        $ema20Alpha = 2 / (20 + 1);
        $ema50Alpha = 2 / (50 + 1);
        $trWindow = [];
        $volumeWindow5 = [];
        $volumeWindow = [];
        $closeWindow3 = [];
        $closeWindow5 = [];
        $closeWindow20 = [];
        $rsiCloseWindow = [];
        $rsiHistory = [];
        $previousClose = null;
        $result = collect();

        foreach ($rows as $index => $row) {
            $close = (float) $row['close_adj'];
            $high = (float) ($row['high_adj'] ?? $close);
            $low = (float) ($row['low_adj'] ?? $close);
            $volume = (int) $row['volume'];

            $ema20 = $ema20 === null ? $close : (($close - $ema20) * $ema20Alpha) + $ema20;
            $ema50 = $ema50 === null ? $close : (($close - $ema50) * $ema50Alpha) + $ema50;

            $tr = null;
            if ($previousClose !== null) {
                $tr = max(
                    $high - $low,
                    abs($high - $previousClose),
                    abs($low - $previousClose),
                );
                $trWindow[] = $tr;
                if (count($trWindow) > 14) {
                    array_shift($trWindow);
                }
            }

            $volumeWindow5[] = $volume;
            if (count($volumeWindow5) > 5) {
                array_shift($volumeWindow5);
            }

            $volumeWindow[] = $volume;
            if (count($volumeWindow) > 20) {
                array_shift($volumeWindow);
            }

            $closeWindow3[] = $close;
            if (count($closeWindow3) > 4) {
                array_shift($closeWindow3);
            }

            $closeWindow5[] = $close;
            if (count($closeWindow5) > 6) {
                array_shift($closeWindow5);
            }

            $closeWindow20[] = $close;
            if (count($closeWindow20) > 21) {
                array_shift($closeWindow20);
            }

            $rsiCloseWindow[] = $close;
            if (count($rsiCloseWindow) > 20) {
                array_shift($rsiCloseWindow);
            }

            $currentRsi = $this->calculateRsi($rsiCloseWindow, 14);
            if ($currentRsi !== null) {
                $rsiHistory[] = $currentRsi;
                if (count($rsiHistory) > 6) {
                    array_shift($rsiHistory);
                }
            }

            $return1 = ($previousClose !== null && $previousClose != 0.0)
                ? round(($close / $previousClose) - 1, 6)
                : null;
            $return3 = count($closeWindow3) >= 4 && $closeWindow3[0] != 0.0
                ? round(($close / $closeWindow3[0]) - 1, 6)
                : null;
            $return5 = count($closeWindow5) >= 6 && $closeWindow5[0] != 0.0
                ? round(($close / $closeWindow5[0]) - 1, 6)
                : null;
            $return20 = count($closeWindow20) >= 21 && $closeWindow20[0] != 0.0
                ? round(($close / $closeWindow20[0]) - 1, 6)
                : null;
            $atr14 = count($trWindow) === 14 ? array_sum($trWindow) / 14 : null;
            $volumeMa5 = count($volumeWindow5) === 5 ? array_sum($volumeWindow5) / 5 : null;
            $volumeMa20 = count($volumeWindow) === 20 ? array_sum($volumeWindow) / 20 : null;
            $rsiSlope5d = count($rsiHistory) === 6
                ? round($currentRsi - $rsiHistory[0], 6)
                : null;
            $atrRatio = ($atr14 !== null && $close != 0.0) ? round($atr14 / $close, 6) : null;
            $volumeRatio20d = ($volumeMa20 !== null && $volumeMa20 != 0.0) ? round($volume / $volumeMa20, 6) : null;

            $result->put($row['date'], [
                'date' => $row['date'],
                'close_adj' => $close,
                'return_1d' => $return1,
                'return_3d' => $return3,
                'return_5d' => $return5,
                'return_20d' => $return20,
                'atr_ratio' => $atrRatio,
                'atr14_pct' => $atrRatio,
                'volume_ratio_5d' => ($volumeMa5 !== null && $volumeMa20 !== null && $volumeMa20 != 0.0) ? round($volumeMa5 / $volumeMa20, 6) : null,
                'volume_ratio_20d' => $volumeRatio20d,
                'price_vs_ema20_pct' => ($index >= 19 && $ema20 != 0.0) ? round(($close / $ema20) - 1, 6) : null,
                'price_vs_ema50' => ($index >= 49 && $ema50 != 0.0) ? round(($close / $ema50) - 1, 6) : null,
                'rsi_slope_5d' => $rsiSlope5d,
                'return_5d_cross_section_rank' => null,
                'volume_spike_flag' => ($volumeMa20 !== null && $volume > ($volumeMa20 * 2)) ? 1 : 0,
            ]);

            $previousClose = $close;
        }

        return $this->stockSeriesCache[$stock->code] = $result;
    }

    protected function ihsgRegimeMap(): Collection
    {
        if ($this->ihsgRegimeCache !== null) {
            return $this->ihsgRegimeCache;
        }

        return $this->ihsgRegimeCache = $this->ihsgRegimeStateMap()
            ->mapWithKeys(fn (array $state, string $date): array => [$date => $state['bullish']]);
    }

    protected function ihsgRegimeStateMap(): Collection
    {
        if ($this->ihsgRegimeStateCache !== null) {
            return $this->ihsgRegimeStateCache;
        }

        if (! is_file($this->ihsgCsvPath)) {
            return $this->ihsgRegimeStateCache = collect();
        }

        $rows = $this->readCsv($this->ihsgCsvPath)
            ->map(fn (array $row): array => [
                'date' => (string) ($row['date'] ?? ''),
                'adj_close' => $this->floatOrNull($row['adj_close'] ?? $row['close'] ?? null),
            ])
            ->filter(fn (array $row): bool => $row['date'] !== '' && $row['adj_close'] !== null)
            ->values();

        $ema50 = null;
        $ema200 = null;
        $alpha50 = 2 / (50 + 1);
        $alpha200 = 2 / (200 + 1);
        $map = collect();
        $lastBullish = null;
        $currentDuration = 0;

        foreach ($rows as $index => $row) {
            $close = (float) $row['adj_close'];
            $ema50 = $ema50 === null ? $close : (($close - $ema50) * $alpha50) + $ema50;
            $ema200 = $ema200 === null ? $close : (($close - $ema200) * $alpha200) + $ema200;

            $bullish = $index >= 199 ? ($ema50 > $ema200) : null;
            if ($bullish === null) {
                $currentDuration = 0;
            } elseif ($lastBullish === null || $bullish !== $lastBullish) {
                $currentDuration = 1;
            } else {
                $currentDuration++;
            }

            $map->put(
                $row['date'],
                [
                    'bullish' => $bullish,
                    'duration' => $bullish === null ? null : $currentDuration,
                ],
            );

            if ($bullish !== null) {
                $lastBullish = $bullish;
            }
        }

        return $this->ihsgRegimeStateCache = $map;
    }

    protected function sentimentWindowStats(
        Stock $stock,
        Collection $articles,
        CarbonInterface $referencePoint,
        int $lookbackDays,
    ): array {
        $periodStart = $referencePoint->copy()->subDays(max(1, $lookbackDays));
        $periodEnd = $referencePoint->copy()->endOfDay();
        $qualityThreshold = (float) config('news.final_quality_threshold', 0.4);
        $available = [];
        $unavailable = 0;

        foreach ($articles as $article) {
            if (! $article->published_at) {
                continue;
            }

            $published = $article->published_at instanceof CarbonInterface
                ? $article->published_at->copy()
                : Carbon::parse($article->published_at);

            if ($published->lt($periodStart) || $published->gt($periodEnd)) {
                continue;
            }

            if ($article->final_quality_score !== null && (float) $article->final_quality_score < $qualityThreshold) {
                continue;
            }

            if (($article->sentiment_method ?? null) === 'python_unavailable') {
                $unavailable++;
                continue;
            }

            $available[] = [
                'score' => (float) ($article->sentiment_score ?? 0.0),
                'weight' => $this->articleWeight($article, $stock, $lookbackDays, $referencePoint),
            ];
        }

        if ($available === []) {
            return [
                'has_sentiment_data' => 0,
                'sentiment_average_5d' => 0.0,
                'weighted_sentiment_5d' => 0.0,
                'news_volume_5d' => 0,
                'sentiment_available_count_5d' => 0,
                'sentiment_unavailable_count_5d' => $unavailable,
            ];
        }

        $scores = array_column($available, 'score');
        $weights = array_column($available, 'weight');
        $weightedSum = 0.0;
        $weightTotal = 0.0;
        foreach ($available as $row) {
            $weightedSum += $row['score'] * $row['weight'];
            $weightTotal += $row['weight'];
        }

        return [
            'has_sentiment_data' => 1,
            'sentiment_average_5d' => round(array_sum($scores) / count($scores), 6),
            'weighted_sentiment_5d' => $weightTotal > 0 ? round($weightedSum / $weightTotal, 6) : 0.0,
            'news_volume_5d' => count($available),
            'sentiment_available_count_5d' => count($available),
            'sentiment_unavailable_count_5d' => $unavailable,
        ];
    }

    protected function articleWeight($article, Stock $stock, int $periodDays, CarbonInterface $referencePoint): float
    {
        $headlineBonus = 0.2;
        $decay = 0.4;

        $weight = 1.0;
        $weight *= max(0.5, (float) ($article->source_weight ?? 1.0));
        $weight *= max(0.1, (float) ($article->relevance_score ?? 1.0));

        if ($this->mentionsStock((string) ($article->title ?? ''), $stock)) {
            $weight += $headlineBonus;
        }

        $daysAgo = $article->published_at
            ? (int) Carbon::parse($article->published_at)->diffInDays($referencePoint)
            : 0;
        $recencyFactor = 1 - (min($daysAgo, $periodDays) / max($periodDays, 1)) * $decay;

        return round($weight * max(0.6, $recencyFactor), 6);
    }

    protected function mentionsStock(string $text, Stock $stock): bool
    {
        $haystack = mb_strtolower($text);
        $code = mb_strtolower($stock->code);
        $name = mb_strtolower((string) $stock->company_name);

        return str_contains($haystack, $code) || ($name !== '' && str_contains($haystack, $name));
    }

    protected function readCsv(string $path): Collection
    {
        $handle = fopen($path, 'rb');
        if ($handle === false) {
            return collect();
        }

        $header = fgetcsv($handle, null, ',', '"', '\\');
        if (! is_array($header)) {
            fclose($handle);
            return collect();
        }

        $rows = [];
        while (($data = fgetcsv($handle, null, ',', '"', '\\')) !== false) {
            if ($data === [null] || $data === false) {
                continue;
            }

            $row = [];
            foreach ($header as $index => $column) {
                $row[$column] = $data[$index] ?? null;
            }
            $rows[] = $row;
        }

        fclose($handle);

        return collect($rows);
    }

    protected function scaledValue(mixed $value, float $factor): ?float
    {
        $numeric = $this->floatOrNull($value);
        if ($numeric === null) {
            return null;
        }

        return round($numeric * $factor, 6);
    }

    protected function floatOrNull(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }

        return (float) $value;
    }

    protected function resolveReferenceDate(CarbonInterface|string|null $referenceDate): CarbonInterface
    {
        if ($referenceDate instanceof CarbonInterface) {
            return $referenceDate;
        }

        if (is_string($referenceDate) && trim($referenceDate) !== '') {
            return Carbon::parse($referenceDate);
        }

        return now();
    }

    protected function calculateRsi(array $closes, int $period = 14): ?float
    {
        if (count($closes) < ($period + 1)) {
            return null;
        }

        $slice = array_slice($closes, -1 * ($period + 1));
        $gains = [];
        $losses = [];

        for ($index = 1; $index < count($slice); $index++) {
            $change = $slice[$index] - $slice[$index - 1];
            if ($change > 0) {
                $gains[] = $change;
                continue;
            }

            $losses[] = abs($change);
        }

        $avgGain = array_sum($gains) / max(count($gains), 1);
        $avgLoss = array_sum($losses) / max(count($losses), 1);

        if ($avgLoss == 0.0) {
            return 70.0;
        }

        $rs = $avgGain / $avgLoss;

        return round(100 - (100 / (1 + $rs)), 6);
    }
}
