<?php

namespace Tests\Feature;

use App\Services\MarketData\MarketBreadthAndMacroService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class MarketBreadthAndMacroTest extends TestCase
{
    use RefreshDatabase;

    public function test_evaluates_high_risk_defensive_when_breadth_weak_and_us_sells_off(): void
    {
        $svc = app(MarketBreadthAndMacroService::class);

        $gate = $svc->evaluateRiskGate(
            [
                'trade_date' => '2026-11-25',
                'total_active' => 800,
                'gainers' => 150,
                'losers' => 600,
                'flat' => 50,
                'gainers_pct' => 18.8,
                'near_arb_count' => 22,
                'total_foreign_net_rp' => -500_000_000_000,
            ],
            [
                'nasdaq' => ['close' => 23217.46, 'chg_pct' => -2.17],
                'sp500' => ['close' => 7111.87, 'chg_pct' => -1.24],
                'usdidr' => ['close' => 18303.0, 'chg_pct' => 0.67],
            ]
        );

        $this->assertSame('HIGH_RISK_DEFENSIVE', $gate['status']);
        $this->assertFalse($gate['allow_bsjp']);
        $this->assertGreaterThanOrEqual(4, $gate['risk_score']);
        $this->assertNotEmpty($gate['flags']);
    }

    public function test_computes_breadth_from_idx_daily_summaries_and_allows_bsjp_when_healthy(): void
    {
        DB::table('idx_daily_summaries')->insert([
            ['trade_date' => '2026-11-25', 'stock_code' => 'BBCA', 'pct_change' => 1.5, 'volume' => 1000, 'value' => 1000000, 'frequency' => 10, 'foreign_buy' => 500, 'foreign_sell' => 200, 'foreign_net' => 300, 'foreign_net_value' => 10_000_000_000, 'source' => 'idx_scrape'],
            ['trade_date' => '2026-11-25', 'stock_code' => 'UNVR', 'pct_change' => 3.8, 'volume' => 1000, 'value' => 1000000, 'frequency' => 10, 'foreign_buy' => 500, 'foreign_sell' => 100, 'foreign_net' => 400, 'foreign_net_value' => 8_000_000_000, 'source' => 'idx_scrape'],
            ['trade_date' => '2026-11-25', 'stock_code' => 'BRPT', 'pct_change' => -2.0, 'volume' => 1000, 'value' => 1000000, 'frequency' => 10, 'foreign_buy' => 100, 'foreign_sell' => 400, 'foreign_net' => -300, 'foreign_net_value' => -5_000_000_000, 'source' => 'idx_scrape'],
        ]);

        $svc = app(MarketBreadthAndMacroService::class);
        $gate = $svc->buildGate([
            'nasdaq' => ['close' => 24000.0, 'chg_pct' => 0.4],
            'usdidr' => ['close' => 18000.0, 'chg_pct' => -0.2],
        ]);

        $this->assertSame('NORMAL', $gate['status']);
        $this->assertTrue($gate['allow_bsjp']);
        $this->assertSame(66.7, $gate['breadth']['gainers_pct']);
        $this->assertSame(13_000_000_000.0, $gate['breadth']['total_foreign_net_rp']);
    }
}
