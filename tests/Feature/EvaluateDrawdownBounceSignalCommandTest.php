<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class EvaluateDrawdownBounceSignalCommandTest extends TestCase
{
    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "OUTCOME: BUMI sinyal #1 horizon 10d -> net +6.20% (exit 2026-08-18)\n"
                ."Selesai. 1 outcome baru diisi.\n"),
        ]);

        $this->artisan('research:evaluate-drawdown-bounce-signal')
            ->expectsOutputToContain('OUTCOME')
            ->expectsOutputToContain('outcome baru diisi')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'evaluate.py');
        });
    }

    public function test_nothing_elapsed_still_exits_successfully(): void
    {
        Process::fake([
            '*' => Process::result(output: "Belum ada horizon yang lewat.\n"),
        ]);

        $this->artisan('research:evaluate-drawdown-bounce-signal')
            ->expectsOutputToContain('Belum ada horizon yang lewat')
            ->assertExitCode(0);
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'yfinance timeout', exitCode: 1),
        ]);

        $this->artisan('research:evaluate-drawdown-bounce-signal')
            ->expectsOutputToContain('Gagal mengevaluasi sinyal')
            ->assertExitCode(1);
    }
}
