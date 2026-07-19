<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;

/**
 * Self-healing companion to scheduler:healthcheck. Reuses the same proxy (storage/logs/scheduler.log
 * last-write time) that already reliably detects "the scheduler/DB was down" (proven across two real
 * outages: 2026-07-10..13 and 2026-07-18..19). When this command finally gets to run again after a
 * gap, it automatically triggers news:backfill-historical for the missed date range, instead of
 * requiring someone to notice the gap and backfill it manually every time.
 */
class AutoRecoverNewsGapCommand extends Command
{
    protected $signature = 'news:auto-recover-gap
        {--threshold-hours=1 : Minimum gap in hours before triggering an automatic backfill}
        {--max-gap-days=14 : Cap how far back a single auto-recovery will backfill}';

    protected $description = 'Detect a news ingestion gap via scheduler.log staleness and automatically backfill the missed date range';

    public function handle(): int
    {
        $path = storage_path('logs/scheduler.log');
        $thresholdHours = max(0, (int) $this->option('threshold-hours'));

        if (! File::exists($path)) {
            $this->line('scheduler.log belum ada, tidak ada baseline untuk deteksi gap. Skip.');

            return self::SUCCESS;
        }

        $lastHealthy = Carbon::createFromTimestamp(File::lastModified($path));
        $hoursSince = $lastHealthy->floatDiffInHours(now());

        if ($hoursSince <= $thresholdHours) {
            $this->line(sprintf('Tidak ada gap terdeteksi (%.2f jam sejak scheduler sehat terakhir).', $hoursSince));

            return self::SUCCESS;
        }

        $maxGapDays = max(1, (int) $this->option('max-gap-days'));
        $earliestAllowed = now()->copy()->subDays($maxGapDays);
        $from = $lastHealthy->lt($earliestAllowed) ? $earliestAllowed : $lastHealthy;
        $to = now();

        $this->warn(sprintf(
            'Gap terdeteksi: %.2f jam sejak scheduler sehat terakhir (%s). Menjalankan backfill otomatis untuk %s..%s.',
            $hoursSince,
            $lastHealthy->toDateTimeString(),
            $from->toDateString(),
            $to->toDateString()
        ));

        $exitCode = Artisan::call('news:backfill-historical', [
            '--from' => $from->toDateString(),
            '--to' => $to->toDateString(),
        ]);

        $this->line(Artisan::output());

        return $exitCode;
    }
}
