<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:fetch-ojk {--limit=50} {--backfill : Fetch OJK articles in a historical date range} {--from=} {--to=} {--scan-limit=} {--debug}')]
#[Description('Ambil berita OJK Pasar Modal dan simpan sebagai berita makro global')]
class FetchOjkNewsCommand extends Command
{
    public function handle(NewsAggregationService $newsAggregationService): int
    {
        $stock = Stock::where('is_active', true)->orderBy('code')->first();
        if (! $stock) {
            $this->error('Tidak ada saham aktif untuk bootstrap fetch OJK.');

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

                return self::FAILURE;
            }

            if ($fromDate->gt($toDate)) {
                [$fromDate, $toDate] = [$toDate->copy()->startOfDay(), $fromDate->copy()->endOfDay()];
            }

            $stats = $newsAggregationService->refreshOjkBackfill($stock, $fromDate, $toDate, $limit, $candidateLimit);
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
        } else {
            $stats = $newsAggregationService->refreshFromProvider($stock, $limit, ['ojk']);

            $this->info(sprintf(
                'OJK RSS: raw %d, saved %d, updated %d, filtered %d, skipped dedup %d',
                $stats['raw'] ?? 0,
                $stats['saved'] ?? 0,
                $stats['updated'] ?? 0,
                $stats['filtered'] ?? 0,
                $stats['skipped_dedup'] ?? 0,
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
}
