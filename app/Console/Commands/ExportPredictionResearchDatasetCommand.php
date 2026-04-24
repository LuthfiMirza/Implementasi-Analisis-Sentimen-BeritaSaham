<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Prediction\ResearchPredictionFeatureService;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;

class ExportPredictionResearchDatasetCommand extends Command
{
    protected $signature = 'prediction:export-research-dataset
        {--ticker=* : Optional stock codes to export}
        {--output=output/prediction_research/dataset.csv : Combined dataset output path}
        {--per-ticker-dir=output/prediction_research/tickers : Per ticker dataset directory}
        {--start-date= : Optional earliest reference date}
        {--end-date= : Optional latest reference date}
        {--horizon=5 : Prediction horizon in trading days}
        {--threshold=0.01 : Flat/up/down threshold in decimal return terms}
        {--min-history=60 : Minimum history rows before a sample is emitted}
        {--include-macro-news : Include macro/global news via forStockContext scope}';

    protected $description = 'Export point-in-time prediction research dataset with adjusted-price features and 5-day direction labels';

    public function __construct(
        protected ResearchPredictionFeatureService $researchPredictionFeatureService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $outputPath = base_path((string) $this->option('output'));
        $perTickerDir = base_path((string) $this->option('per-ticker-dir'));
        $horizon = max(1, (int) $this->option('horizon'));
        $threshold = max(0.0, (float) $this->option('threshold'));
        $minHistory = max(20, (int) $this->option('min-history'));
        $startDate = $this->option('start-date') ? Carbon::parse((string) $this->option('start-date'))->toDateString() : null;
        $endDate = $this->option('end-date') ? Carbon::parse((string) $this->option('end-date'))->toDateString() : null;
        $includeMacroNews = (bool) $this->option('include-macro-news');
        $requestedTickers = collect((array) $this->option('ticker'))
            ->filter(fn ($code) => is_string($code) && trim($code) !== '')
            ->map(fn (string $code) => strtoupper(trim($code)))
            ->values();

        $stocks = Stock::query()
            ->when($requestedTickers->isNotEmpty(), fn ($query) => $query->whereIn('code', $requestedTickers->all()))
            ->orderBy('code')
            ->get();

        if ($stocks->isEmpty()) {
            $this->error('No stocks matched the requested export scope.');
            return self::FAILURE;
        }

        $this->ensureDirectory(dirname($outputPath));
        $this->ensureDirectory($perTickerDir);

        $combinedRows = [];
        $exportedTickers = 0;
        $skippedTickers = 0;

        /** @var Stock $stock */
        foreach ($stocks as $stock) {
            $series = $this->researchPredictionFeatureService->seriesForStock($stock);
            if ($series->count() < ($minHistory + $horizon + 1)) {
                $skippedTickers++;
                $this->line(sprintf('Skip %s: insufficient adjusted history (%d rows).', $stock->code, $series->count()));
                continue;
            }

            $seriesValues = $series->values();
            $articles = NewsArticle::with('source')
                ->forStockContext($stock, $includeMacroNews)
                ->whereNotNull('published_at')
                ->orderBy('published_at')
                ->get();

            $tickerRows = [];
            for ($index = $minHistory; $index < ($seriesValues->count() - $horizon); $index++) {
                $row = $seriesValues[$index];
                $futureRow = $seriesValues[$index + $horizon];
                $referenceDate = $row['date'];

                if (($startDate !== null && $referenceDate < $startDate) || ($endDate !== null && $referenceDate > $endDate)) {
                    continue;
                }

                $features = $this->researchPredictionFeatureService->buildForDate($stock, $articles, $referenceDate);
                if ($this->hasMissingCoreFeature($features)) {
                    continue;
                }

                $closeNow = (float) ($row['close_adj'] ?? 0.0);
                $closeFuture = (float) ($futureRow['close_adj'] ?? 0.0);
                if ($closeNow <= 0.0 || $closeFuture <= 0.0) {
                    continue;
                }

                $futureReturn = ($closeFuture / $closeNow) - 1;
                $tickerRows[] = array_merge([
                    'ticker' => $stock->code,
                    'reference_date' => $referenceDate,
                    'future_return_5d' => round($futureReturn, 6),
                    'target_direction_5d' => $this->labelDirection($futureReturn, $threshold),
                ], $this->orderedFeatureColumns($features));
            }

            if ($tickerRows === []) {
                $skippedTickers++;
                $this->line(sprintf('Skip %s: no exportable point-in-time rows after filters.', $stock->code));
                continue;
            }

            $this->writeCsv($perTickerDir.DIRECTORY_SEPARATOR.$stock->code.'.csv', $tickerRows);
            array_push($combinedRows, ...$tickerRows);
            $exportedTickers++;
            $this->info(sprintf('Exported %s prediction dataset (%d rows).', $stock->code, count($tickerRows)));
        }

        if ($combinedRows === []) {
            $this->error('No dataset rows were produced.');
            return self::FAILURE;
        }

        usort($combinedRows, fn (array $left, array $right): int => [$left['reference_date'], $left['ticker']] <=> [$right['reference_date'], $right['ticker']]);
        $this->writeCsv($outputPath, $combinedRows);

        $this->info(sprintf('Combined dataset written to %s (%d rows, %d tickers, %d skipped).', $outputPath, count($combinedRows), $exportedTickers, $skippedTickers));

        return self::SUCCESS;
    }

    protected function orderedFeatureColumns(array $features): array
    {
        $ordered = [];
        foreach (ResearchPredictionFeatureService::FEATURE_COLUMNS as $column) {
            $ordered[$column] = $features[$column] ?? null;
        }

        $ordered['sentiment_available_count_5d'] = $features['sentiment_available_count_5d'] ?? 0;
        $ordered['sentiment_unavailable_count_5d'] = $features['sentiment_unavailable_count_5d'] ?? 0;
        $ordered['prediction_feature_version'] = $features['prediction_feature_version'] ?? null;
        $ordered['adjusted_price_basis'] = $features['adjusted_price_basis'] ?? null;

        return $ordered;
    }

    protected function hasMissingCoreFeature(array $features): bool
    {
        foreach (['return_5d', 'return_20d', 'atr14_pct', 'volume_ratio_20d', 'price_vs_ema50', 'market_regime_bullish'] as $required) {
            if (! array_key_exists($required, $features) || $features[$required] === null) {
                return true;
            }
        }

        return false;
    }

    protected function labelDirection(float $futureReturn, float $threshold): string
    {
        if ($futureReturn >= $threshold) {
            return 'up';
        }

        if ($futureReturn <= (-1 * $threshold)) {
            return 'down';
        }

        return 'flat';
    }

    protected function writeCsv(string $path, array $rows): void
    {
        if ($rows === []) {
            return;
        }

        $handle = fopen($path, 'wb');
        if ($handle === false) {
            throw new \RuntimeException('Unable to open CSV for writing: '.$path);
        }

        fputcsv($handle, array_keys($rows[0]));
        foreach ($rows as $row) {
            fputcsv($handle, $row);
        }

        fclose($handle);
    }

    protected function ensureDirectory(string $path): void
    {
        if (! is_dir($path)) {
            mkdir($path, 0777, true);
        }
    }
}
