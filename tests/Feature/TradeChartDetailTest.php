<?php

namespace Tests\Feature;

use App\Models\StockPrice;
use App\Models\Trade;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class TradeChartDetailTest extends TestCase
{
    public function test_guest_is_redirected_from_trade_detail_and_chart_data(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BRPT');
        $trade = Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'BRPT',
            'status' => 'open',
            'entry_price' => 655,
            'entry_date' => '2026-11-18',
        ]);

        $this->get("/trades/{$trade->id}")->assertRedirect('/login');
        $this->get("/trades/{$trade->id}/chart-data")->assertRedirect('/login');
    }

    public function test_user_cannot_view_another_users_trade_detail(): void
    {
        $owner = $this->user();
        $other = $this->user();
        $stock = $this->seedStock('DEWA');
        $trade = Trade::factory()->create([
            'user_id' => $owner->id,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'status' => 'open',
            'entry_price' => 228,
            'entry_date' => '2026-11-18',
        ]);

        $this->actingAs($other)->get("/trades/{$trade->id}")->assertForbidden();
        $this->actingAs($other)->getJson("/trades/{$trade->id}/chart-data")->assertForbidden();
    }

    public function test_authenticated_user_can_view_trade_detail_page_and_daily_chart_data(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BRPT');

        // Seed 35 daily bars so MA20, RSI14, and MACD(12,26,9) all compute cleanly
        $baseDate = Carbon::parse('2026-10-01');
        for ($i = 0; $i < 35; $i++) {
            $price = 650 + ($i % 7) * 10;
            if ($i === 32) {
                $price = 710; // peak after entry
            }
            StockPrice::create([
                'stock_id' => $stock->id,
                'price_date' => $baseDate->copy()->addDays($i)->toDateString(),
                'open' => $price - 5,
                'high' => $price + 10,
                'low' => $price - 10,
                'close' => $price,
                'volume' => $i === 30 ? 5000000 : 1000000,
                'source' => 'test',
                'interval_type' => '1d',
            ]);
        }

        $trade = Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'BRPT',
            'strategy_label' => 'gabungan',
            'signal_quality' => 'A+',
            'status' => 'open',
            'entry_price' => 655,
            'stop_loss' => 632,
            'target_1' => 688,
            'target_2' => 714,
            'lot_size' => 15000,
            'position_value' => 9825000,
            'entry_date' => $baseDate->copy()->addDays(30)->toDateString(),
        ]);

        $this->actingAs($user)
            ->get("/trades/{$trade->id}")
            ->assertOk()
            ->assertSee('BRPT')
            ->assertSee('RSI (14) Wilder')
            ->assertSee('MACD (12, 26, 9)')
            ->assertSee('Hard Stop Loss');

        $resp = $this->actingAs($user)->getJson("/trades/{$trade->id}/chart-data?tf=1d");
        $resp->assertOk()
            ->assertJsonPath('timeframe', '1d')
            ->assertJsonPath('trade.ticker', 'BRPT')
            ->assertJsonPath('levels.entry', 655)
            ->assertJsonPath('levels.stop_loss', 632)
            ->assertJsonPath('levels.trailing_active', true);

        $json = $resp->json();
        $this->assertCount(35, $json['candles']);
        $this->assertNotEmpty($json['ma20']);
        $this->assertNotEmpty($json['rsi14']);
        $this->assertNotEmpty($json['macd']['macd']);
        $this->assertNotEmpty($json['markers']);
        $this->assertEquals(720, $json['levels']['peak_price']);
        $this->assertEquals(round(720 * 0.98, 2), $json['levels']['trailing_stop']);
    }

    public function test_intraday_15m_chart_data_returns_bars_and_markers(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('CENT');

        $times = [
            '2026-11-17 15:30:00',
            '2026-11-17 15:45:00',
            '2026-11-18 09:00:00',
            '2026-11-18 09:15:00',
            '2026-11-18 09:30:00',
            '2026-11-18 09:45:00',
        ];
        foreach ($times as $idx => $barTime) {
            DB::table('intraday_prices')->insert([
                'stock_code' => 'CENT',
                'interval' => '15m',
                'bar_time' => $barTime,
                'open' => 74 + $idx,
                'high' => 75 + $idx,
                'low' => 73 + $idx,
                'close' => 74 + $idx,
                'volume' => 1000000 + $idx * 200000,
                'source' => 'test',
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        $trade = Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'CENT',
            'strategy_label' => 'bsjp',
            'signal_quality' => 'A+',
            'status' => 'closed',
            'entry_price' => 74,
            'exit_price' => 79,
            'stop_loss' => 72,
            'target_1' => 76,
            'pnl_percent' => 6.76,
            'result' => 'trailing_stop',
            'entry_date' => '2026-11-17',
            'exit_date' => '2026-11-18',
            'closed_at' => '2026-11-18 09:30:00',
        ]);

        $resp = $this->actingAs($user)->getJson("/trades/{$trade->id}/chart-data?tf=15m");
        $resp->assertOk()
            ->assertJsonPath('timeframe', '15m')
            ->assertJsonPath('has_intraday', true)
            ->assertJsonPath('fallback_to_daily', false);

        $json = $resp->json();
        $this->assertCount(6, $json['candles']);
        $this->assertGreaterThanOrEqual(2, count($json['markers']));
    }
}
