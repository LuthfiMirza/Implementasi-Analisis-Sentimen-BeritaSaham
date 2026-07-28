<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CollectForeignFlowSnapshotCommandTest extends TestCase
{
    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "net_buy: 5 saham -> IATA, BACH, BRPT, RAJA, SCMA\n"
                ."net_sell: 5 saham -> BUMI, BUKA, PADI, BNBR, DSSA\n"
                ."\nTersimpan ke quant/foreign_flow_tracker/snapshots.jsonl\n"),
        ]);

        $this->artisan('research:collect-foreign-flow')
            ->expectsOutputToContain('net_buy: 5 saham')
            ->expectsOutputToContain('Tersimpan ke')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'collect_snapshot.py');
        });
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'Kedua fetch gagal', exitCode: 1),
        ]);

        $this->artisan('research:collect-foreign-flow')
            ->expectsOutputToContain('Gagal mengumpulkan snapshot')
            ->assertExitCode(1);
    }
}
