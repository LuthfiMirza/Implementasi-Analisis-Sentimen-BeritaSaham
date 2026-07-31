<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class DetectDrawdownBounceSignalCommandTest extends TestCase
{
    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "SIGNAL BARU: BUMI (tracked) trigger 2026-08-03 -> entry 2026-08-04 @ 160\n"
                ."1 sinyal baru dicatat. Total tercatat: 1.\n"),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('SIGNAL BARU')
            ->expectsOutputToContain('sinyal baru dicatat')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'detect_signal.py');
        });
    }

    public function test_no_new_signal_still_exits_successfully(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada sinyal baru. Tidak ada trigger sejak 2026-07-31. Total tercatat: 0.\n"),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('Tidak ada sinyal baru')
            ->assertExitCode(0);
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'yfinance timeout', exitCode: 1),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('Gagal mendeteksi sinyal')
            ->assertExitCode(1);
    }
}
