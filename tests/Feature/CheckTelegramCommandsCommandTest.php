<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CheckTelegramCommandsCommandTest extends TestCase
{
    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "Diproses: /close BUMI 172 -> BUMI ditutup dari pemantauan\n1 perintah diproses.\n"),
        ]);

        $this->artisan('research:check-telegram-commands')
            ->expectsOutputToContain('perintah diproses')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'telegram_commands.py');
        });
    }

    public function test_no_new_commands_still_exits_successfully(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada perintah baru.\n"),
        ]);

        $this->artisan('research:check-telegram-commands')
            ->expectsOutputToContain('Tidak ada perintah baru')
            ->assertExitCode(0);
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'Telegram API timeout', exitCode: 1),
        ]);

        $this->artisan('research:check-telegram-commands')
            ->expectsOutputToContain('Gagal cek perintah Telegram')
            ->assertExitCode(1);
    }
}
