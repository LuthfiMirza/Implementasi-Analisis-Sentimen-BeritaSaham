<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class AutoRecoverNewsGapCommandTest extends TestCase
{
    use RefreshDatabase;

    private string $path;

    private ?string $backup = null;

    private bool $existed = false;

    protected function setUp(): void
    {
        parent::setUp();
        $this->path = storage_path('logs/scheduler.log');
        $this->existed = File::exists($this->path);
        $this->backup = $this->existed ? File::get($this->path) : null;
    }

    protected function tearDown(): void
    {
        if ($this->existed) {
            File::put($this->path, $this->backup);
        } elseif (File::exists($this->path)) {
            File::delete($this->path);
        }
        parent::tearDown();
    }

    public function test_no_gap_detected_when_log_recently_written(): void
    {
        File::put($this->path, 'test');
        touch($this->path);

        $this->artisan('news:auto-recover-gap', ['--threshold-hours' => 1])
            ->expectsOutputToContain('Tidak ada gap terdeteksi')
            ->assertExitCode(0);
    }

    public function test_gap_detected_triggers_backfill(): void
    {
        File::put($this->path, 'test');
        touch($this->path, now()->subHours(5)->timestamp);

        // No Stock rows seeded, so the triggered news:backfill-historical iterates zero tickers
        // (safe no-op, no real network calls) -- this test only verifies gap DETECTION, not the
        // backfill fetcher internals (covered separately by BackfillHistoricalNewsCommand's own tests).
        $this->artisan('news:auto-recover-gap', ['--threshold-hours' => 1])
            ->expectsOutputToContain('Gap terdeteksi')
            ->assertExitCode(0);
    }

    public function test_missing_scheduler_log_skips_silently(): void
    {
        if (File::exists($this->path)) {
            File::delete($this->path);
        }

        $this->artisan('news:auto-recover-gap')
            ->expectsOutputToContain('belum ada')
            ->assertExitCode(0);
    }

    public function test_gap_is_capped_at_max_gap_days(): void
    {
        File::put($this->path, 'test');
        touch($this->path, now()->subDays(30)->timestamp);

        $this->artisan('news:auto-recover-gap', ['--threshold-hours' => 1, '--max-gap-days' => 14])
            ->expectsOutputToContain(now()->subDays(14)->toDateString())
            ->assertExitCode(0);
    }
}
