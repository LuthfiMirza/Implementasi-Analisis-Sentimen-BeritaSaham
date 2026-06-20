<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\News\BusinessSiteSearchFetcher;
use App\Services\News\FinnhubNewsFetcher;
use App\Services\News\GdeltFetcher;
use App\Services\News\GNewsFetcher;
use App\Services\News\GoogleNewsRssFetcher;
use App\Services\News\NewsAggregationService;
use App\Services\News\NewsApiFetcher;
use App\Services\News\StockKeywordMapper;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Cache;

#[Signature('news:backfill-historical {--from=} {--to=} {--ticker=*} {--source=*} {--dry-run} {--delay=2} {--limit=100}')]
#[Description('Backfill berita historis dengan date-range fetcher dan mode dry-run aman')]
class BackfillHistoricalNewsCommand extends Command
{
    protected array $defaultSources = ['gdelt', 'google_news_rss', 'business_site_search'];
    protected array $historicalSources = ['gdelt', 'newsapi', 'gnews', 'finnhub'];

    public function handle(NewsAggregationService $aggregationService): int
    {
        $fromOption = $this->option('from');
        $toOption = $this->option('to');
        if (! $fromOption || ! $toOption) {
            $this->error('Option --from dan --to wajib diisi, contoh: --from=2025-10-01 --to=2026-04-15');
            return self::FAILURE;
        }

        $from = Carbon::parse($fromOption)->startOfDay();
        $to = Carbon::parse($toOption)->endOfDay();
        if ($from->gt($to)) {
            $this->error('--from tidak boleh setelah --to.');
            return self::FAILURE;
        }

        $sources = $this->option('source') ?: $this->defaultSources;
        $dryRun = (bool) $this->option('dry-run');
        $tickers = collect($this->option('ticker'))->map(fn ($ticker) => strtoupper($ticker))->filter()->values();
        $targetTickers = $tickers->isNotEmpty()
            ? $tickers
            : collect(['ADRO', 'ASII', 'BBCA', 'BBRI', 'BMRI', 'GOTO', 'ICBP', 'INDF', 'TLKM', 'UNVR']);
        $stocks = $this->resolveStocks($targetTickers->all(), $dryRun);
        $baseDelay = max(0, (int) $this->option('delay'));
        $limit = max(1, (int) $this->option('limit'));
        $months = $this->monthChunks($from, $to);
        $totalRequests = 0;
        $doneWithData = 0;
        $doneEmpty = 0;
        $failedRetry = 0;
        $skippedDone = 0;
        $mapper = new StockKeywordMapper();

        $this->line('Historical news backfill '.($dryRun ? 'DRY-RUN' : 'LIVE'));
        $this->line("Range: {$from->toDateString()} - {$to->toDateString()}");
        $this->line('Sources: '.implode(', ', $sources));
        $this->line('Tickers: '.$stocks->pluck('code')->implode(', '));

        foreach ($sources as $source) {
            if (! in_array($source, [...$this->defaultSources, ...$this->historicalSources], true)) {
                $this->warn("Skip source tidak dikenal: {$source}");
                continue;
            }

            $effectiveDelay = $this->effectiveDelaySeconds($source, $baseDelay);
            $this->line("Effective delay {$source}: {$effectiveDelay}s");
            $sourceRequests = 0;
            $sourcePlanned = 0;
            $sourceSkipped = 0;
            foreach ($stocks as $stock) {
                $requestCount = $this->estimateRequests($source, $months);
                $sourceRequests += $requestCount;
                $totalRequests += $requestCount;
                $this->line("- {$source} {$stock->code}: {$requestCount} request (".$this->formatMonths($months).')');

                foreach ($months as [$chunkFrom, $chunkTo]) {
                    $key = "news-backfill:{$source}:{$stock->code}:{$chunkFrom->toDateString()}:{$chunkTo->toDateString()}";
                    if (Cache::get($key) === 'done') {
                        $sourceSkipped++;
                        $skippedDone++;
                        $this->line("  resume skip {$stock->code} {$source} {$chunkFrom->toDateString()}..{$chunkTo->toDateString()}".($dryRun ? ' (dry-run)' : ''));
                        continue;
                    }

                    $sourcePlanned++;

                    if ($dryRun) {
                        continue;
                    }

                    $articles = $this->fetchHistorical($source, $stock, $mapper, $chunkFrom, $chunkTo, $limit);
                    if ($articles === null) {
                        $failedRetry++;
                        $this->warn("  failed {$stock->code} {$source} {$chunkFrom->toDateString()}..{$chunkTo->toDateString()}; will retry on next run");
                    } else {
                        $stats = $aggregationService->persistHistoricalArticles($stock, $articles, $source);
                        Cache::forever($key, 'done');
                        if ($stats['raw'] > 0) {
                            $doneWithData++;
                        } else {
                            $doneEmpty++;
                        }
                        $this->line("  saved {$stock->code} {$source}: raw {$stats['raw']}, saved {$stats['saved']}, updated {$stats['updated']}");
                    }

                    if ($effectiveDelay > 0) {
                        sleep($effectiveDelay);
                    }
                }
            }

            $this->line("Subtotal {$source}: {$sourceRequests} request");
            if ($dryRun) {
                $this->line("Dry-run {$source}: planned {$sourcePlanned}, skipped_done {$sourceSkipped}");
            }
        }

        $this->line("Estimated total requests: {$totalRequests}");
        if (! $dryRun) {
            $this->line('Backfill result summary:');
            $this->line("- done_with_data: {$doneWithData}");
            $this->line("- done_empty: {$doneEmpty}");
            $this->line("- failed_retry_next_run: {$failedRetry}");
            $this->line("- skipped_already_done: {$skippedDone}");
        }
        $this->warn('Concern: NewsAPI/GNews free tier dapat menolak range historis lama; fetcher akan log error provider.');

        return self::SUCCESS;
    }

    protected function effectiveDelaySeconds(string $source, int $requestedDelay): int
    {
        if ($source === 'gdelt') {
            return max($requestedDelay, (int) config('news.gdelt.min_delay_seconds', 6));
        }

        return $requestedDelay;
    }

    protected function fetchHistorical(string $source, Stock $stock, StockKeywordMapper $mapper, Carbon $from, Carbon $to, int $limit): ?array
    {
        return match ($source) {
            'gdelt' => (new GdeltFetcher($mapper))->fetchHistorical($mapper->queryString($stock), $from, $to, min($limit, 250)),
            'google_news_rss' => (new GoogleNewsRssFetcher($mapper))->fetchHistorical($stock, $from, $to, $limit),
            'business_site_search' => (new BusinessSiteSearchFetcher($mapper))->fetchHistorical($stock, $from, $to, $limit),
            'newsapi' => (new NewsApiFetcher($mapper))->fetchHistorical($stock, $from, $to, $limit),
            'gnews' => (new GNewsFetcher($mapper))->fetchHistorical($stock, $from, $to, $limit),
            'finnhub' => (new FinnhubNewsFetcher())->fetchHistorical($stock->code, $from, $to, $limit),
            default => tap([], fn () => $this->warn("Source {$source} belum punya date-range fetcher; hanya dihitung pada dry-run.")),
        };
    }

    protected function filterArticlesByDate(?array $articles, Carbon $from, Carbon $to): ?array
    {
        if ($articles === null) {
            return null;
        }

        return collect($articles)
            ->filter(function (array $article) use ($from, $to) {
                $publishedAt = $article['published_at'] ?? null;
                if (! $publishedAt) {
                    return false;
                }

                try {
                    $date = $publishedAt instanceof Carbon ? $publishedAt : Carbon::parse($publishedAt);
                } catch (\Throwable) {
                    return false;
                }

                return $date->betweenIncluded($from, $to);
            })
            ->values()
            ->all();
    }

    protected function resolveStocks(array $tickers, bool $dryRun)
    {
        try {
            return Stock::whereIn('code', $tickers)->get();
        } catch (\Throwable $e) {
            if (! $dryRun) {
                throw $e;
            }

            $this->warn('Database tidak tersedia; dry-run memakai ticker target tanpa metadata emiten.');

            return collect($tickers)->map(function (string $ticker) {
                $stock = new Stock();
                $stock->code = $ticker;
                $stock->company_name = $ticker;

                return $stock;
            });
        }
    }

    protected function estimateRequests(string $source, array $months): int
    {
        return match ($source) {
            'gdelt', 'finnhub' => count($months),
            'newsapi', 'gnews' => count($months),
            default => count($months),
        };
    }

    protected function monthChunks(Carbon $from, Carbon $to): array
    {
        $chunks = [];
        $cursor = $from->copy()->startOfDay();
        while ($cursor->lte($to)) {
            $chunkTo = $cursor->copy()->endOfMonth()->min($to->copy());
            $chunks[] = [$cursor->copy(), $chunkTo->copy()];
            $cursor = $chunkTo->copy()->addDay()->startOfDay();
        }

        return $chunks;
    }

    protected function formatMonths(array $months): string
    {
        return collect($months)
            ->map(fn ($range) => $range[0]->format('Y-m').'='.$range[0]->toDateString().'..'.$range[1]->toDateString())
            ->implode(', ');
    }
}
