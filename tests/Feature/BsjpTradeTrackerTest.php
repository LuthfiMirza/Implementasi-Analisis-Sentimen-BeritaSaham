<?php

namespace Tests\Feature;

use App\Models\BsjpTradeLog;
use Carbon\Carbon;
use Tests\TestCase;

class BsjpTradeTrackerTest extends TestCase
{
    public function test_bsjp_tracker_page_renders_successfully_for_authenticated_user(): void
    {
        $user = $this->user();
        $this->seedStock('DYAN');

        $response = $this->actingAs($user)->get('/trades/bsjp-tracker');

        $response->assertOk();
        $response->assertSee('Pencatatan Portofolio BSJP');
        $response->assertSee('20.000.000');
    }

    public function test_can_log_bsjp_buy_order_with_20m_capital(): void
    {
        $user = $this->user();
        $this->seedStock('DYAN');

        $response = $this->actingAs($user)->post('/trades/bsjp-tracker/buy', [
            'ticker' => 'DYAN',
            'signal_date' => '2026-09-22',
            'entry_price' => 105,
            'capital' => 20000000,
            'category' => 'sweetspot',
            'notes' => 'Masuk sore 15:50 WIB',
        ]);

        $response->assertRedirect();

        // At Rp 105 per share:
        // 1 lot with fee = 105 * 100 * 1.0015 = 10.515,75
        // floor(20.000.000 / 10515.75) = 1.901 lot
        $this->assertDatabaseHas('bsjp_trade_logs', [
            'ticker' => 'DYAN',
            'status' => 'OPEN',
            'entry_price' => 105,
            'lots' => 1901,
            'capital_allocated' => 20000000,
        ]);
    }

    public function test_can_log_bsjp_buy_order_without_signal_date_falls_back_to_today(): void
    {
        $user = $this->user();
        $this->seedStock('PSDN');

        $response = $this->actingAs($user)->post('/trades/bsjp-tracker/buy', [
            'ticker' => 'PSDN',
            'entry_price' => 144,
            'category' => 'sweetspot',
            'target_tp' => 148,
            'stop_loss' => 140,
        ]);

        $response->assertRedirect();

        $this->assertDatabaseHas('bsjp_trade_logs', [
            'ticker' => 'PSDN',
            'status' => 'OPEN',
            'entry_price' => 144,
        ]);

        $log = BsjpTradeLog::where('ticker', 'PSDN')->first();
        $this->assertNotNull($log);
        $this->assertEquals(now('Asia/Jakarta')->toDateString(), $log->signal_date->toDateString());
    }

    public function test_can_log_bsjp_sell_order_and_calculates_pnl_correctly(): void
    {
        $user = $this->user();
        $this->seedStock('CENT');

        // 1.800 lot at Rp 110 = Rp 19.800.000 capital
        $trade = BsjpTradeLog::create([
            'signal_date' => Carbon::yesterday('Asia/Jakarta')->toDateString(),
            'ticker' => 'CENT',
            'stock_name' => 'Centratama Telekomunikasi Tbk.',
            'category' => 'sweetspot',
            'signal_price' => 110,
            'entry_price' => 110,
            'entry_at' => Carbon::yesterday('Asia/Jakarta')->setTime(15, 50),
            'lots' => 1800,
            'capital_allocated' => 19800000,
            'target_tp' => 113,
            'stop_loss' => 107,
            'status' => 'OPEN',
        ]);

        // Sell at target 113 (+2.73% gross)
        $response = $this->actingAs($user)->post("/trades/bsjp-tracker/{$trade->id}/sell", [
            'exit_price' => 113,
            'exit_type' => 'OPEN_MARKET',
            'notes' => 'Cuan pagi terwujud di 09:00 WIB',
        ]);

        $response->assertRedirect();

        $trade->refresh();
        $this->assertEquals('CLOSED', $trade->status);
        $this->assertEquals(113, $trade->exit_price);
        $this->assertEquals(2.73, $trade->gross_pnl_pct);
        $this->assertGreaterThan(0, $trade->net_pnl_rp);
        $this->assertGreaterThan(2.0, $trade->net_pnl_pct);
    }

    public function test_can_skip_bsjp_trade(): void
    {
        $user = $this->user();
        $this->seedStock('BSSR');

        $trade = BsjpTradeLog::create([
            'signal_date' => Carbon::now('Asia/Jakarta')->toDateString(),
            'ticker' => 'BSSR',
            'stock_name' => 'Baramulti Suksessarana Tbk.',
            'category' => 'rocket',
            'signal_price' => 3800,
            'entry_price' => 3800,
            'lots' => 52,
            'capital_allocated' => 19760000,
            'status' => 'OPEN',
        ]);

        $response = $this->actingAs($user)->post("/trades/bsjp-tracker/{$trade->id}/skip");

        $response->assertRedirect();

        $trade->refresh();
        $this->assertEquals('SKIPPED', $trade->status);
    }

    public function test_evaluate_bsjp_artisan_command_runs_safely(): void
    {
        $stock = $this->seedStock('DSFI');
        $this->seedPriceSeries($stock, 30, 100);

        $trade = BsjpTradeLog::create([
            'signal_date' => Carbon::yesterday('Asia/Jakarta')->toDateString(),
            'ticker' => 'DSFI',
            'stock_name' => 'Dharma Samudera Fishing Tbk.',
            'category' => 'sweetspot',
            'signal_price' => 100,
            'entry_price' => 100,
            'lots' => 2000,
            'capital_allocated' => 20000000,
            'status' => 'OPEN',
        ]);

        $this->artisan('trade:evaluate-bsjp', ['--force' => true])
            ->assertSuccessful();

        $this->assertEquals('OPEN', $trade->fresh()->status);
    }
}
