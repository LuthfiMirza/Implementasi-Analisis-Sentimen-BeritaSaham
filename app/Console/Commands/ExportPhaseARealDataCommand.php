<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;
use Illuminate\Support\Str;

class ExportPhaseARealDataCommand extends Command
{
    private const BASE_CSV_COLUMNS = [
        'date',
        'open',
        'high',
        'low',
        'close',
        'volume',
    ];

    private const SENTIMENT_CSV_COLUMNS = [
        'sentiment_average_1d',
        'sentiment_weighted_1d',
        'sentiment_news_count_1d',
    ];

    private const SENTIMENT_EMPTY_ROW = [
        'sentiment_average_1d' => 0.0,
        'sentiment_weighted_1d' => 0.0,
        'sentiment_news_count_1d' => 0,
    ];

    protected $signature = 'phase-a:export-real-data
        {--data-dir=data : Target directory for per-ticker OHLCV CSV files}
        {--metadata-file= : Optional metadata CSV path, default <data-dir>/ticker_metadata.csv}
        {--interval=1d : Price interval to export}
        {--min-rows=50 : Minimum OHLCV rows required per ticker}
        {--include-sentiment-series : Append daily sentiment aggregates for the limited item-7 experiment}
        {--include-inactive : Include inactive stocks as well}';

    protected $description = 'Export real stock_prices rows into the CSV dataset expected by the Phase A quant pipeline';

    public function handle(): int
    {
        $dataDir = base_path((string) $this->option('data-dir'));
        $metadataOption = trim((string) $this->option('metadata-file'));
        $metadataPath = $metadataOption !== ''
            ? base_path($metadataOption)
            : $dataDir.DIRECTORY_SEPARATOR.'ticker_metadata.csv';
        $interval = trim((string) $this->option('interval')) ?: '1d';
        $minRows = max(1, (int) $this->option('min-rows'));
        $includeSentimentSeries = (bool) $this->option('include-sentiment-series');

        if (! is_dir($dataDir)) {
            mkdir($dataDir, 0777, true);
        }
        $metadataDirectory = dirname($metadataPath);
        if (! is_dir($metadataDirectory)) {
            mkdir($metadataDirectory, 0777, true);
        }

        $stocks = Stock::query()
            ->when(
                ! $this->option('include-inactive'),
                fn ($query) => $query->where('is_active', true)
            )
            ->orderBy('code')
            ->get();

        $exportedTickers = 0;
        $skippedTickers = 0;
        $metadataRows = [];

        /** @var \App\Models\Stock $stock */
        foreach ($stocks as $stock) {
            $rows = $this->normalizePriceRows(StockPrice::query()
                ->where('stock_id', $stock->id)
                ->where('interval_type', $interval)
                ->orderBy('price_date')
                ->get(['price_date', 'open', 'high', 'low', 'close', 'volume', 'source']));

            if ($rows->count() < $minRows) {
                $skippedTickers++;
                $this->line(sprintf(
                    'Skip %s: only %d rows for interval %s (minimum %d).',
                    $stock->code,
                    $rows->count(),
                    $interval,
                    $minRows
                ));
                continue;
            }

            $dailySentimentSeries = $includeSentimentSeries
                ? $this->buildDailySentimentSeries($stock, $rows)
                : [];
            $csvRows = $this->buildTickerRows($rows, $dailySentimentSeries, $includeSentimentSeries);
            $tickerPath = $dataDir.DIRECTORY_SEPARATOR.$stock->code.'.csv';
            $this->writeCsv($tickerPath, $csvRows);
            $sentimentCoverage = $this->summarizeSentimentCoverage($dailySentimentSeries);

            $firstDate = $rows->first()?->price_date;
            $lastDate = $rows->last()?->price_date;
            $normalizedSector = $this->normalizeSector($stock->sector);

            $metadataRows[] = [
                'ticker' => $stock->code,
                'sector' => $normalizedSector,
                'category' => $this->mapCategoryFromSector($stock->sector),
                'company_name' => $stock->company_name,
                'interval_type' => $interval,
                'rows_1d' => $rows->count(),
                'date_start' => $firstDate ? Carbon::parse($firstDate)->toDateString() : null,
                'date_end' => $lastDate ? Carbon::parse($lastDate)->toDateString() : null,
                'export_source' => 'laravel_stock_prices',
                'sentiment_series_included' => $includeSentimentSeries ? 'yes' : 'no',
                'sentiment_columns' => $includeSentimentSeries
                    ? implode('|', self::SENTIMENT_CSV_COLUMNS)
                    : null,
                'sentiment_alignment' => $includeSentimentSeries
                    ? 'trade_date_window_prev_trade_exclusive_current_trade_inclusive'
                    : null,
                'sentiment_fill_policy' => $includeSentimentSeries
                    ? 'zero_score_and_zero_count_when_no_articles'
                    : null,
                'sentiment_trade_date_start' => $includeSentimentSeries
                    ? ($firstDate ? Carbon::parse($firstDate)->toDateString() : null)
                    : null,
                'sentiment_trade_date_end' => $includeSentimentSeries
                    ? ($lastDate ? Carbon::parse($lastDate)->toDateString() : null)
                    : null,
                'sentiment_days_with_articles' => $includeSentimentSeries
                    ? $sentimentCoverage['days_with_articles']
                    : null,
                'sentiment_article_count_total' => $includeSentimentSeries
                    ? $sentimentCoverage['article_count_total']
                    : null,
            ];

            $exportedTickers++;
            $this->info(sprintf('Exported %s to %s (%d rows).', $stock->code, $tickerPath, count($csvRows)));
        }

        if ($exportedTickers === 0) {
            $this->error('No ticker satisfied the export requirements. Nothing was written.');

            return self::FAILURE;
        }

        $this->writeCsv($metadataPath, $metadataRows);

        $this->info(sprintf('Exported %d ticker CSV files.', $exportedTickers));
        $this->line(sprintf('Skipped %d tickers below minimum rows.', $skippedTickers));
        $this->line('Metadata: '.$metadataPath);

        return self::SUCCESS;
    }

    protected function buildTickerRows(
        Collection $rows,
        array $dailySentimentSeries = [],
        bool $includeSentimentSeries = false,
    ): array
    {
        return $rows
            ->map(function (StockPrice $price) use ($dailySentimentSeries, $includeSentimentSeries): array {
                $tradeDate = Carbon::parse($price->price_date)->toDateString();
                $row = [
                    'date' => $tradeDate,
                    'open' => (float) $price->open,
                    'high' => (float) $price->high,
                    'low' => (float) $price->low,
                    'close' => (float) $price->close,
                    'volume' => (int) $price->volume,
                ];

                if ($includeSentimentSeries) {
                    $sentiment = $dailySentimentSeries[$tradeDate] ?? self::SENTIMENT_EMPTY_ROW;
                    foreach (self::SENTIMENT_CSV_COLUMNS as $column) {
                        $row[$column] = $column === 'sentiment_news_count_1d'
                            ? (int) $sentiment[$column]
                            : (float) $sentiment[$column];
                    }
                }

                $columnOrder = $includeSentimentSeries
                    ? array_merge(self::BASE_CSV_COLUMNS, self::SENTIMENT_CSV_COLUMNS)
                    : self::BASE_CSV_COLUMNS;

                return collect($columnOrder)
                    ->mapWithKeys(fn (string $column): array => [$column => $row[$column]])
                    ->all();
            })
            ->values()
            ->all();
    }

    protected function normalizePriceRows(Collection $rows): Collection
    {
        $normalizedRows = $rows;
        if ($rows->contains(fn (StockPrice $price) => (($price->source ?? '') !== 'seed'))) {
            $normalizedRows = $rows
                ->filter(fn (StockPrice $price) => (($price->source ?? '') !== 'seed'))
                ->values();
        }

        return $normalizedRows
            ->groupBy(fn (StockPrice $price) => Carbon::parse($price->price_date)->toDateString())
            ->map(function (Collection $group) {
                return $group
                    ->sort(function (StockPrice $left, StockPrice $right): int {
                        $leftRank = $this->sourcePriority($left);
                        $rightRank = $this->sourcePriority($right);

                        if ($leftRank !== $rightRank) {
                            return $leftRank <=> $rightRank;
                        }

                        return Carbon::parse($right->price_date)->getTimestamp()
                            <=> Carbon::parse($left->price_date)->getTimestamp();
                    })
                    ->first();
            })
            ->sortBy(fn (StockPrice $price) => Carbon::parse($price->price_date)->getTimestamp())
            ->values();
    }

    protected function sourcePriority(StockPrice $price): int
    {
        if (($price->source ?? '') === 'seed') {
            return 2;
        }

        if (($price->source ?? null) === null) {
            return 0;
        }

        return 1;
    }

    protected function buildDailySentimentSeries(Stock $stock, Collection $priceRows): array
    {
        if ($priceRows->isEmpty()) {
            return [];
        }

        $qualityThreshold = (float) config('news.final_quality_threshold', 0.4);
        $firstTradeDate = Carbon::parse($priceRows->first()->price_date)->startOfDay();
        $lastTradeDate = Carbon::parse($priceRows->last()->price_date)->endOfDay();

        $articlesByDate = NewsArticle::query()
            ->where('stock_id', $stock->id)
            ->whereNotNull('published_at')
            ->whereBetween('published_at', [$firstTradeDate, $lastTradeDate])
            ->orderBy('published_at')
            ->get([
                'published_at',
                'sentiment_label',
                'sentiment_score',
                'relevance_score',
                'source_weight',
                'final_quality_score',
            ])
            ->filter(function (NewsArticle $article) use ($qualityThreshold): bool {
                return $article->final_quality_score === null
                    || (float) $article->final_quality_score >= $qualityThreshold;
            })
            ->groupBy(fn (NewsArticle $article) => Carbon::parse($article->published_at)->toDateString());

        $series = [];
        $previousTradeDate = null;

        /** @var \App\Models\StockPrice $price */
        foreach ($priceRows as $price) {
            $tradeDate = Carbon::parse($price->price_date)->toDateString();
            $windowArticles = collect();

            foreach ($articlesByDate as $articleDate => $articles) {
                if (
                    ($previousTradeDate === null || $articleDate > $previousTradeDate)
                    && $articleDate <= $tradeDate
                ) {
                    $windowArticles = $windowArticles->concat($articles);
                }
            }

            $series[$tradeDate] = $this->summarizeSentimentWindow($windowArticles);
            $previousTradeDate = $tradeDate;
        }

        return $series;
    }

    protected function summarizeSentimentWindow(Collection $articles): array
    {
        if ($articles->isEmpty()) {
            return self::SENTIMENT_EMPTY_ROW;
        }

        $scores = $articles->map(fn (NewsArticle $article): float => $this->resolveSentimentScore($article));
        $weightedSum = 0.0;
        $totalWeight = 0.0;

        /** @var \App\Models\NewsArticle $article */
        foreach ($articles as $article) {
            $score = $this->resolveSentimentScore($article);
            $relevance = max(0.1, (float) ($article->relevance_score ?? 1.0));
            $sourceWeight = max(0.5, (float) ($article->source_weight ?? 1.0));
            $effectiveWeight = $relevance * $sourceWeight;

            $weightedSum += $score * $effectiveWeight;
            $totalWeight += $effectiveWeight;
        }

        return [
            'sentiment_average_1d' => round((float) $scores->avg(), 4),
            'sentiment_weighted_1d' => $totalWeight > 0
                ? round($weightedSum / $totalWeight, 4)
                : 0.0,
            'sentiment_news_count_1d' => $articles->count(),
        ];
    }

    protected function summarizeSentimentCoverage(array $dailySentimentSeries): array
    {
        $daysWithArticles = 0;
        $articleCountTotal = 0;

        foreach ($dailySentimentSeries as $payload) {
            $count = (int) ($payload['sentiment_news_count_1d'] ?? 0);
            if ($count > 0) {
                $daysWithArticles++;
            }
            $articleCountTotal += $count;
        }

        return [
            'days_with_articles' => $daysWithArticles,
            'article_count_total' => $articleCountTotal,
        ];
    }

    protected function resolveSentimentScore(NewsArticle $article): float
    {
        if ($article->sentiment_score !== null) {
            return (float) $article->sentiment_score;
        }

        return match ($article->sentiment_label) {
            'positive' => 1.0,
            'negative' => -1.0,
            default => 0.0,
        };
    }

    protected function writeCsv(string $path, array $rows): void
    {
        $handle = fopen($path, 'wb');
        if ($handle === false) {
            throw new \RuntimeException('Failed to open CSV for writing: '.$path);
        }

        try {
            if (empty($rows)) {
                return;
            }

            fputcsv($handle, array_keys($rows[0]));
            foreach ($rows as $row) {
                fputcsv($handle, $row);
            }
        } finally {
            fclose($handle);
        }
    }

    protected function normalizeSector(?string $sector): string
    {
        $normalized = Str::of((string) $sector)->trim()->squish()->lower()->slug('_')->value();

        return $normalized !== '' ? $normalized : 'unknown';
    }

    protected function mapCategoryFromSector(?string $sector): string
    {
        $normalized = $this->normalizeSector($sector);

        return match ($normalized) {
            'perbankan' => 'finance',
            'teknologi' => 'technology',
            'energi' => 'energy',
            'telekomunikasi' => 'telco',
            'pertambangan' => 'mining',
            'otomotif' => 'automotive',
            'konsumsi' => 'consumer',
            default => $normalized,
        };
    }
}
