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
}
