<?php

namespace Tests\Feature;

use App\Models\Trade;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CheckTelegramCommandsCommandTest extends TestCase
{
    private string $cachePath;

    protected function setUp(): void
    {
        parent::setUp();

        $this->cachePath = base_path('quant/drawdown_bounce_tracker/closed_trades_cache.json');
    }

    protected function tearDown(): void
    {
        if (is_file($this->cachePath)) {
            unlink($this->cachePath);
        }

        parent::tearDown();
    }

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

    public function test_run_refreshes_closed_trades_cache_for_history_command(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada perintah baru.\n"),
        ]);

        Trade::factory()->closeState()->create(['ticker' => 'BUMI']);
        Trade::factory()->create(['ticker' => 'DEWA', 'status' => 'open']); // still open, must be excluded

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertFileExists($this->cachePath);
        $cached = json_decode(file_get_contents($this->cachePath), true);

        $this->assertCount(1, $cached);
        $this->assertSame('BUMI', $cached[0]['ticker']);
    }

    public function test_run_still_succeeds_when_no_closed_trades_exist(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada perintah baru.\n"),
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertFileExists($this->cachePath);
        $this->assertSame([], json_decode(file_get_contents($this->cachePath), true));
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
