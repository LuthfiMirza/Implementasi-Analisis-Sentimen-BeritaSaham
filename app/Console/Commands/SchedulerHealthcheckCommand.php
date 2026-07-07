<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\File;

/**
 * Reports whether the Laravel scheduler (routes/console.php) appears to be actually running, by
 * checking when storage/logs/scheduler.log was last written to. The scheduler only produces log
 * lines when `php artisan schedule:run` executes (via cron or `schedule:work`), so a stale log file
 * is a reliable proxy for "the scheduler has stopped running" -- which silently starves the news
 * pipeline (Gap 1) without any other visible symptom.
 */
class SchedulerHealthcheckCommand extends Command
{
    protected $signature = 'scheduler:healthcheck {--max-hours=3 : Hours since last scheduler.log write before this is reported unhealthy}';

    protected $description = 'Check whether storage/logs/scheduler.log has been updated recently (proxy for "is the scheduler actually running")';

    public function handle(): int
    {
        $path = storage_path('logs/scheduler.log');
        $maxHours = (int) $this->option('max-hours');

        if (! File::exists($path)) {
            $this->error("scheduler.log tidak ditemukan di {$path}. Scheduler kemungkinan belum pernah jalan sama sekali.");

            return self::FAILURE;
        }

        $lastModified = Carbon::createFromTimestamp(File::lastModified($path));
        $hoursSince = round($lastModified->floatDiffInHours(now()), 2);

        $this->line("scheduler.log terakhir diupdate: {$lastModified->toDateTimeString()} ({$hoursSince} jam lalu)");

        if ($hoursSince > $maxHours) {
            $this->error("UNHEALTHY: lebih dari {$maxHours} jam sejak scheduler terakhir jalan. Cek apakah cron/schedule:work masih aktif.");

            return self::FAILURE;
        }

        $this->info('OK: scheduler tampak masih aktif jalan.');

        return self::SUCCESS;
    }
}
