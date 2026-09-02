<?php

namespace Tests\Feature;

use App\Models\IdxDailySummary;
use Tests\TestCase;

class MarketAlertsPageTest extends TestCase
{
    private function seedSpike(): void
    {
        for ($i = 3; $i <= 14; $i++) {
            IdxDailySummary::create([
                'trade_date' => now()->subDays($i)->toDateString(),
                'stock_code' => 'BBCA', 'stock_name' => 'Bank Central Asia',
                'previous' => 1000, 'open' => 1000, 'high' => 1000, 'low' => 1000, 'close' => 1000,
                'change' => 0, 'pct_change' => 0, 'volume' => 1_000_000, 'value' => 5_000_000_000,
                'frequency' => 100, 'source' => 'test',
            ]);
        }
        IdxDailySummary::create([
            'trade_date' => now()->toDateString(),
            'stock_code' => 'BBCA', 'stock_name' => 'Bank Central Asia',
            'previous' => 1000, 'open' => 1000, 'high' => 1100, 'low' => 1000, 'close' => 1080,
            'change' => 80, 'pct_change' => 8, 'volume' => 6_000_000, 'value' => 6_000_000_000,
            'frequency' => 900, 'foreign_buy' => 5_000_000, 'foreign_sell' => 100_000,
            'foreign_net' => 4_900_000, 'foreign_net_value' => 4_900_000 * 1080, 'source' => 'test',
        ]);
    }

    public function test_guest_is_redirected_to_login(): void
    {
        $this->get('/market-alerts')->assertRedirect('/login');
    }

    public function test_authenticated_user_sees_the_page_with_disclaimer(): void
    {
        $this->seedSpike();

        $this->actingAsUser()->get('/market-alerts')
            ->assertOk()
            ->assertSee('Market Alerts')
            ->assertSee('bukan sinyal atau rekomendasi', false);
    }

    public function test_data_endpoint_returns_alert_lists_as_json(): void
    {
        $this->seedSpike();

        $this->actingAsUser()->getJson('/market-alerts/data')
            ->assertOk()
            ->assertJsonPath('trade_date', now()->toDateString())
            ->assertJsonPath('volume.0.stock_code', 'BBCA')
            ->assertJsonStructure(['trade_date', 'counts', 'volume', 'gap', 'foreign', 'ownership']);
    }

    public function test_page_renders_without_data(): void
    {
        $this->actingAsUser()->get('/market-alerts')->assertOk();
    }

    public function test_foreign_history_endpoint_returns_per_day_rows(): void
    {
        foreach (['2026-08-27' => -2_000_000, '2026-08-28' => 3_000_000, '2026-08-31' => 5_000_000] as $d => $net) {
            IdxDailySummary::create([
                'trade_date' => $d, 'stock_code' => 'BBRI', 'stock_name' => 'Bank Rakyat Indonesia',
                'previous' => 3000, 'open' => 3000, 'high' => 3000, 'low' => 3000, 'close' => 3000,
                'change' => 0, 'pct_change' => 0, 'volume' => 1_000_000, 'value' => 50_000_000_000, 'frequency' => 100,
                'foreign_buy' => max(0, $net), 'foreign_sell' => max(0, -$net),
                'foreign_net' => $net, 'foreign_net_value' => $net * 3000, 'source' => 'test',
            ]);
        }

        $this->actingAsUser()->getJson('/market-alerts/foreign-history?code=BBRI&days=20')
            ->assertOk()
            ->assertJsonPath('stock_code', 'BBRI')
            ->assertJsonPath('summary.buy_days', 2)
            ->assertJsonPath('summary.streak', 2)
            ->assertJsonPath('summary.streak_dir', 'buy')
            ->assertJsonCount(3, 'days');
    }

    public function test_foreign_history_endpoint_rejects_bad_code(): void
    {
        $this->actingAsUser()->getJson('/market-alerts/foreign-history?code=not-a-ticker!')
            ->assertStatus(422);
    }
}
