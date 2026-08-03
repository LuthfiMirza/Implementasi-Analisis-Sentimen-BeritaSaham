<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CheckTrailingStopAlertCommandTest extends TestCase
{
    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "BUMI: entry 159 (2026-07-29) | puncak 173 (2026-08-03) | harga sekarang 168 (2026-08-03) | mundur 2.9%\n"),
        ]);

        $this->artisan('research:check-trailing-stop-alert')
            ->expectsOutputToContain('BUMI')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'check_trailing_stop.py');
        });
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'yfinance timeout', exitCode: 1),
        ]);

        $this->artisan('research:check-trailing-stop-alert')
            ->expectsOutputToContain('Gagal cek trailing stop')
            ->assertExitCode(1);
    }
}
