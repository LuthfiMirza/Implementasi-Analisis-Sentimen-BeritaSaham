<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\File;
use Tests\TestCase;

class SchedulerHealthcheckCommandTest extends TestCase
{
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

    public function test_reports_ok_when_log_recently_written(): void
    {
        File::put($this->path, 'test');
        touch($this->path);

        $this->artisan('scheduler:healthcheck', ['--max-hours' => 3])
            ->assertExitCode(0);
    }

    public function test_reports_unhealthy_when_log_missing(): void
    {
        if (File::exists($this->path)) {
            File::delete($this->path);
        }

        $this->artisan('scheduler:healthcheck')
            ->assertExitCode(1);
    }

    public function test_reports_unhealthy_when_log_older_than_max_hours(): void
    {
        File::put($this->path, 'test');
        touch($this->path, now()->subHours(5)->timestamp);

        $this->artisan('scheduler:healthcheck', ['--max-hours' => 3])
            ->assertExitCode(1);
    }
}
