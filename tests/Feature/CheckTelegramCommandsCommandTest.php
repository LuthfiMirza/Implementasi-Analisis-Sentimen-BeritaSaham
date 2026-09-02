<?php

namespace Tests\Feature;

use App\Models\Trade;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CheckTelegramCommandsCommandTest extends TestCase
{
    private string $cachePath;

    private string $positionsPath;

    private ?string $positionsBackup = null;

    protected function setUp(): void
    {
        parent::setUp();

        $this->cachePath = base_path('quant/drawdown_bounce_tracker/closed_trades_cache.json');
        $this->positionsPath = base_path('quant/drawdown_bounce_tracker/open_positions.json');
        $this->positionsBackup = is_file($this->positionsPath) ? file_get_contents($this->positionsPath) : null;
    }

    protected function tearDown(): void
    {
        if (is_file($this->cachePath)) {
            unlink($this->cachePath);
        }

        if ($this->positionsBackup !== null) {
            file_put_contents($this->positionsPath, $this->positionsBackup);
        }

        parent::tearDown();
    }

    /** @param  array<int, array<string, mixed>>  $positions */
    private function writePositions(array $positions): void
    {
        file_put_contents($this->positionsPath, json_encode($positions, JSON_PRETTY_PRINT));
    }

    /** @return array<int, array<string, mixed>> */
    private function readPositions(): array
    {
        return json_decode((string) file_get_contents($this->positionsPath), true) ?: [];
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

        $this->assertSame(1, $cached['overall']['total_trades']);
        $this->assertCount(1, $cached['recent']);
        $this->assertSame('BUMI', $cached['recent'][0]['ticker']);
    }

    public function test_run_still_succeeds_when_no_closed_trades_exist(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada perintah baru.\n"),
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertFileExists($this->cachePath);
        $cached = json_decode(file_get_contents($this->cachePath), true);
        $this->assertSame(0, $cached['overall']['total_trades']);
        $this->assertSame([], $cached['recent']);
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

    // Fase DF: tombol "⏭️ Skip" di alert sinyal -- telegram_commands.py cetak
    // "SYNC_SKIP|TICKER|STRATEGI|TANGGAL", trade OPEN yang cocok (ticker+strategy_label+entry_date)
    // WAJIB dihapus SEPENUHNYA (bukan close) dari Trade Journal.
    public function test_sync_skip_deletes_matching_open_trade(): void
    {
        Process::fake([
            '*' => Process::result(output: "SYNC_SKIP|BUMI|MOMENTUM|2026-08-26\n1 perintah diproses.\n"),
        ]);

        $trade = Trade::factory()->create([
            'ticker' => 'BUMI',
            'strategy_label' => 'momentum',
            'entry_date' => '2026-08-26',
            'status' => 'open',
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertDatabaseMissing('trades', ['id' => $trade->id]);
    }

    public function test_sync_skip_does_not_touch_trade_with_different_strategy_same_ticker(): void
    {
        // BUMI bisa punya posisi GABUNGAN dan MOMENTUM bersamaan (Fase CR dedup key) -- Skip
        // MOMENTUM TIDAK BOLEH ikut menghapus posisi GABUNGAN yang beda strategi.
        Process::fake([
            '*' => Process::result(output: "SYNC_SKIP|BUMI|MOMENTUM|2026-08-26\n1 perintah diproses.\n"),
        ]);

        $momentumTrade = Trade::factory()->create([
            'ticker' => 'BUMI', 'strategy_label' => 'momentum', 'entry_date' => '2026-08-26', 'status' => 'open',
        ]);
        $gabunganTrade = Trade::factory()->create([
            'ticker' => 'BUMI', 'strategy_label' => 'gabungan', 'entry_date' => '2026-08-26', 'status' => 'open',
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertDatabaseMissing('trades', ['id' => $momentumTrade->id]);
        $this->assertDatabaseHas('trades', ['id' => $gabunganTrade->id]);
    }

    public function test_sync_skip_skips_gracefully_when_no_matching_open_trade(): void
    {
        Process::fake([
            '*' => Process::result(output: "SYNC_SKIP|DSSA|GABUNGAN|2026-08-26\n1 perintah diproses.\n"),
        ]);

        // Tidak ada trade DSSA sama sekali -- harus tidak error, cuma warn.
        $this->artisan('research:check-telegram-commands')->assertExitCode(0);
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

    public function test_reconcile_drops_positions_that_are_closed_in_the_journal(): void
    {
        Process::fake(['*' => Process::result(output: "Tidak ada perintah baru.\n")]);

        Trade::factory()->closeState()->create([
            'ticker' => 'BUMI', 'strategy_label' => 'momentum', 'entry_date' => '2026-08-19',
        ]);
        Trade::factory()->create([
            'ticker' => 'DEWA', 'strategy_label' => 'bottom_rebound', 'entry_date' => '2026-08-28', 'status' => 'open',
        ]);

        $this->writePositions([
            ['ticker' => 'BUMI', 'entry_date' => '2026-08-19', 'entry_price' => 183, 'strategy' => 'MOMENTUM'],
            ['ticker' => 'DEWA', 'entry_date' => '2026-08-28', 'entry_price' => 440, 'strategy' => 'BOTTOM_REBOUND', 'milestone_peak' => 462],
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $kept = collect($this->readPositions());
        $this->assertFalse($kept->contains(fn ($p) => $p['ticker'] === 'BUMI'), 'BUMI (closed) harus dibuang');
        $dewa = $kept->firstWhere('ticker', 'DEWA');
        $this->assertNotNull($dewa, 'DEWA (open) harus tetap ada');
        $this->assertSame(462, $dewa['milestone_peak'], 'state tracking DEWA harus utuh');
    }

    public function test_reconcile_keeps_recent_orphans_but_drops_stale_ones(): void
    {
        Process::fake(['*' => Process::result(output: "Tidak ada perintah baru.\n")]);
        Trade::factory()->create(['ticker' => 'BBCA', 'status' => 'open']); // supaya tabel tidak kosong

        $this->writePositions([
            ['ticker' => 'ESSA', 'entry_date' => now()->subDays(20)->toDateString(), 'entry_price' => 635, 'strategy' => 'GABUNGAN'],
            ['ticker' => 'RAJA', 'entry_date' => now()->subDays(2)->toDateString(), 'entry_price' => 820, 'strategy' => 'GABUNGAN'],
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $kept = collect($this->readPositions())->pluck('ticker');
        $this->assertNotContains('ESSA', $kept, 'orphan basi (20 hari) harus dibuang');
        $this->assertContains('RAJA', $kept, 'orphan muda (2 hari) harus dibiarkan');
    }

    public function test_reconcile_leaves_positions_untouched_when_db_has_no_trades(): void
    {
        Process::fake(['*' => Process::result(output: "Tidak ada perintah baru.\n")]);

        $this->writePositions([
            ['ticker' => 'BUMI', 'entry_date' => '2026-01-01', 'entry_price' => 183, 'strategy' => 'MOMENTUM'],
        ]);

        $this->artisan('research:check-telegram-commands')->assertExitCode(0);

        $this->assertCount(1, $this->readPositions(), 'tanpa trade di DB, JSON tidak boleh disentuh');
    }
}
