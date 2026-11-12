<?php

namespace Tests\Feature;

use App\Models\Trade;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class CheckTrailingStopAlertCommandTest extends TestCase
{
    use RefreshDatabase;

    private string $cachePath;

    private string $positionsPath;

    private ?string $positionsBackup = null;

    private ?string $cacheBackup = null;

    protected function setUp(): void
    {
        parent::setUp();

        $this->cachePath = base_path('quant/drawdown_bounce_tracker/closed_trades_cache.json');
        $this->positionsPath = base_path('quant/drawdown_bounce_tracker/open_positions.json');
        $this->positionsBackup = is_file($this->positionsPath) ? file_get_contents($this->positionsPath) : null;
        $this->cacheBackup = is_file($this->cachePath) ? file_get_contents($this->cachePath) : null;
    }

    protected function tearDown(): void
    {
        if ($this->positionsBackup !== null) {
            file_put_contents($this->positionsPath, $this->positionsBackup);
        }

        if ($this->cacheBackup !== null) {
            file_put_contents($this->cachePath, $this->cacheBackup);
        }

        parent::tearDown();
    }

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

    public function test_auto_closes_open_trade_when_sync_alert_close_emitted(): void
    {
        $trade = Trade::factory()->create([
            'ticker' => 'BUMI',
            'strategy_label' => 'gabungan',
            'entry_price' => 125,
            'stop_loss' => 120.63,
            'lot_size' => 800,
            'entry_date' => '2026-10-19 09:00:00',
            'status' => 'open',
        ]);

        Process::fake([
            '*' => Process::result(output: "SYNC_ALERT_CLOSE|BUMI|143.08|2026-10-27 10:15:00|trailing_stop|GABUNGAN|2026-10-19\n"),
        ]);

        $this->artisan('research:check-trailing-stop-alert')
            ->expectsOutputToContain('Auto-Close 3-Lapis Proteksi')
            ->assertExitCode(0);

        $trade->refresh();
        $this->assertSame('closed', $trade->status);
        $this->assertSame('trailing_stop', $trade->result);
        $this->assertEquals(143.08, (float) $trade->exit_price);
    }

    public function test_sync_alert_close_scopes_to_matching_strategy_when_same_ticker_and_date_exist(): void
    {
        $gabunganTrade = Trade::factory()->create([
            'ticker' => 'DEWA',
            'strategy_label' => 'gabungan',
            'entry_price' => 232,
            'stop_loss' => 223.88,
            'lot_size' => 43100,
            'entry_date' => '2026-11-10 09:00:00',
            'status' => 'open',
        ]);

        $reboundTrade = Trade::factory()->create([
            'ticker' => 'DEWA',
            'strategy_label' => 'bottom_rebound',
            'entry_price' => 234,
            'stop_loss' => 225.81,
            'lot_size' => 42700,
            'entry_date' => '2026-11-10 09:00:00',
            'status' => 'open',
        ]);

        Process::fake([
            '*' => Process::result(output: "SYNC_ALERT_CLOSE|DEWA|239.12|2026-11-11 10:15:00|trailing_stop|BOTTOM_REBOUND|2026-11-10\n"),
        ]);

        $this->artisan('research:check-trailing-stop-alert')->assertExitCode(0);

        $gabunganTrade->refresh();
        $reboundTrade->refresh();

        $this->assertSame('open', $gabunganTrade->status);
        $this->assertSame('closed', $reboundTrade->status);
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
