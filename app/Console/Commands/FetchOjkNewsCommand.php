<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:fetch-ojk {--limit=50} {--backfill : Fetch OJK articles in a historical date range} {--from=} {--to=} {--scan-limit=} {--debug} {--output-dir=output}')]
#[Description('Ambil berita OJK Pasar Modal dan simpan sebagai berita makro global')]
class FetchOjkNewsCommand extends Command
{
    public function handle(NewsAggregationService $newsAggregationService): int
    {
        $outputDir = base_path((string) $this->option('output-dir'));
        if (! is_dir($outputDir)) {
            mkdir($outputDir, 0777, true);
        }

        $stock = Stock::where('is_active', true)->orderBy('code')->first();
        if (! $stock) {
            $this->error('Tidak ada saham aktif untuk bootstrap fetch OJK.');
            $this->writeBackfillArtifacts($outputDir, [
                'requested_range' => $this->requestedRangePayload(),
                'fetched_count' => 0,
                'saved_count' => 0,
                'updated_count' => 0,
                'skipped_count' => 0,
                'final_article_count' => $this->currentOjkArticleCount(),
                'backfill_status' => 'empty',
                'blocker_reason' => 'no_active_stock_for_bootstrap',
                'next_action' => 'Pastikan ada satu saham aktif untuk bootstrap lalu rerun php artisan news:fetch-ojk.',
            ]);

            return self::FAILURE;
        }

        $limit = (int) $this->option('limit');
        $isBackfill = (bool) $this->option('backfill') || $this->option('from') || $this->option('to');
        $candidateLimit = $this->option('scan-limit') !== null ? (int) $this->option('scan-limit') : null;

        if ($isBackfill) {
            $from = $this->option('from') ?: now()->subMonths(2)->toDateString();
            $to = $this->option('to') ?: now()->toDateString();

            try {
                $fromDate = Carbon::parse($from)->startOfDay();
                $toDate = Carbon::parse($to)->endOfDay();
            } catch (\Throwable $e) {
                $this->error('Format tanggal --from/--to tidak valid.');
                $this->writeBackfillArtifacts($outputDir, [
                    'requested_range' => ['from' => $from, 'to' => $to],
                    'fetched_count' => 0,
                    'saved_count' => 0,
                    'updated_count' => 0,
                    'skipped_count' => 0,
                    'final_article_count' => $this->currentOjkArticleCount(),
                    'backfill_status' => 'empty',
                    'blocker_reason' => 'invalid_date_range',
                    'next_action' => 'Gunakan format tanggal YYYY-MM-DD untuk --from dan --to lalu rerun php artisan news:fetch-ojk.',
                ]);

                return self::FAILURE;
            }

            if ($fromDate->gt($toDate)) {
                [$fromDate, $toDate] = [$toDate->copy()->startOfDay(), $fromDate->copy()->endOfDay()];
            }

            $stats = $newsAggregationService->refreshOjkBackfill($stock, $fromDate, $toDate, $limit, $candidateLimit);
            $payload = $this->buildBackfillPayload($stats, $fromDate, $toDate);
            $this->writeBackfillArtifacts($outputDir, $payload);
            $this->info(sprintf(
                'OJK backfill %s..%s: raw %d, saved %d, updated %d, filtered %d, skipped dedup %d',
                $fromDate->toDateString(),
                $toDate->toDateString(),
                $stats['raw'] ?? 0,
                $stats['saved'] ?? 0,
                $stats['updated'] ?? 0,
                $stats['filtered'] ?? 0,
                $stats['skipped_dedup'] ?? 0,
            ));
            $this->line(sprintf(
                'Backfill status: %s | final_article_count: %d | blocker_reason: %s',
                $payload['backfill_status'],
                $payload['final_article_count'],
                $payload['blocker_reason'] ?? 'none'
            ));
        } else {
            $stats = $newsAggregationService->refreshFromProvider($stock, $limit, ['ojk']);
            $payload = $this->buildBackfillPayload($stats, null, null);
            $this->writeBackfillArtifacts($outputDir, $payload);

            $this->info(sprintf(
                'OJK RSS: raw %d, saved %d, updated %d, filtered %d, skipped dedup %d',
                $stats['raw'] ?? 0,
                $stats['saved'] ?? 0,
                $stats['updated'] ?? 0,
                $stats['filtered'] ?? 0,
                $stats['skipped_dedup'] ?? 0,
            ));
            $this->line(sprintf(
                'Backfill status: %s | final_article_count: %d | blocker_reason: %s',
                $payload['backfill_status'],
                $payload['final_article_count'],
                $payload['blocker_reason'] ?? 'none'
            ));
        }

        if ($this->option('debug')) {
            $this->line('Provider breakdown: '.json_encode($stats['by_provider'] ?? []));
            if (! empty($stats['dropped_samples'])) {
                $this->line('Dropped samples: '.json_encode($stats['dropped_samples']));
            }
        }

        return self::SUCCESS;
    }

    protected function buildBackfillPayload(array $stats, ?CarbonInterface $fromDate, ?CarbonInterface $toDate): array
    {
        $fetchedCount = (int) ($stats['raw'] ?? 0);
        $savedCount = (int) ($stats['saved'] ?? 0);
        $updatedCount = (int) ($stats['updated'] ?? 0);
        $skippedCount = max(0, $fetchedCount - $savedCount - $updatedCount);
        $finalArticleCount = $this->currentOjkArticleCount();
        $backfillStatus = 'ready';
        $blockerReason = null;
        $nextAction = 'none';

        if ($fetchedCount <= 0) {
            $backfillStatus = 'empty';
            $blockerReason = 'ojk_source_empty';
            $nextAction = 'Periksa sumber OJK/date range, lalu rerun php artisan news:fetch-ojk --backfill.';
        } elseif ($finalArticleCount <= 0) {
            $backfillStatus = 'empty';
            $blockerReason = 'ojk_articles_not_persisted';
            $nextAction = 'Periksa filter relevansi/dedup OJK lalu rerun backfill.';
        } elseif ($savedCount + $updatedCount <= 0 || $finalArticleCount < (int) config('analytics.phase_a_closeout.min_ojk_article_count', 5)) {
            $backfillStatus = 'partial';
            $blockerReason = 'ojk_backfill_partial';
            $nextAction = 'Perluas rentang backfill OJK atau turunkan loss akibat filter, lalu rerun closeout.';
        }

        return [
            'generated_at' => now()->toIso8601String(),
            'requested_range' => [
                'from' => $fromDate?->toDateString(),
                'to' => $toDate?->toDateString(),
            ],
            'fetched_count' => $fetchedCount,
            'saved_count' => $savedCount,
            'updated_count' => $updatedCount,
            'skipped_count' => $skippedCount,
            'filtered_count' => (int) ($stats['filtered'] ?? 0),
            'skipped_dedup_count' => (int) ($stats['skipped_dedup'] ?? 0),
            'final_article_count' => $finalArticleCount,
            'backfill_status' => $backfillStatus,
            'blocker_reason' => $blockerReason,
            'next_action' => $nextAction,
        ];
    }

    protected function currentOjkArticleCount(): int
    {
        return (int) NewsArticle::query()
            ->whereNull('stock_id')
            ->where('source_provider', 'ojk_rss')
            ->count();
    }

    protected function requestedRangePayload(): array
    {
        return [
            'from' => $this->option('from') ?: null,
            'to' => $this->option('to') ?: null,
        ];
    }

    protected function writeBackfillArtifacts(string $outputDir, array $payload): void
    {
        $jsonPath = $outputDir.'/ojk_backfill_status.json';
        $reportPath = $outputDir.'/ojk_backfill_report.txt';

        file_put_contents($jsonPath, json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        file_put_contents($reportPath, $this->buildBackfillReport($payload));
    }

    protected function buildBackfillReport(array $payload): string
    {
        $range = (array) ($payload['requested_range'] ?? []);

        return implode("\n", [
            'OJK Backfill Report',
            '===================',
            '',
            '- requested_from='.($range['from'] ?? 'n/a'),
            '- requested_to='.($range['to'] ?? 'n/a'),
            '- fetched_count='.(int) ($payload['fetched_count'] ?? 0),
            '- saved_count='.(int) ($payload['saved_count'] ?? 0),
            '- updated_count='.(int) ($payload['updated_count'] ?? 0),
            '- skipped_count='.(int) ($payload['skipped_count'] ?? 0),
            '- final_article_count='.(int) ($payload['final_article_count'] ?? 0),
            '- backfill_status='.($payload['backfill_status'] ?? 'unknown'),
            '- blocker_reason='.($payload['blocker_reason'] ?? 'none'),
            '- next_action='.($payload['next_action'] ?? 'none'),
            '',
        ]);
    }
}
