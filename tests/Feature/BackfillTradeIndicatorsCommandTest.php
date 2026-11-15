<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Models\Trade;
use App\Models\User;
use App\Services\Trading\TradeQualityGraderService;
use Tests\TestCase;

class BackfillTradeIndicatorsCommandTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        User::factory()->create(['id' => 2]);
    }

    public function test_quality_grader_service_assigns_grade_correctly(): void
    {
        $grader = app(TradeQualityGraderService::class);

        // Grade A+: High volume + good wick + optimal RSI on Tier S stock
        $gradedA = $grader->gradeTrade('DEWA', 'gabungan', [
            'vol_ratio_ma20' => 1.5,
            'lower_wick_pct' => 1.8,
            'rsi_14' => 35.0,
            'sub_signal' => 'drawdown',
        ]);

        $this->assertSame('A+', $gradedA['grade']);
        $this->assertGreaterThanOrEqual(80, $gradedA['quality_score']);
        $this->assertSame(100, $gradedA['recommended_sizing_pct']);
        $this->assertSame('A_SERAPAN_IDEAL (1.0%-3.0%)', $gradedA['snapshot']['wick_scenario']);

        // Grade C: Blacklisted / Dead Low / dry volume
        $gradedC = $grader->gradeTrade('PSAB', 'gabungan', [
            'vol_ratio_ma20' => 0.4,
            'lower_wick_pct' => 0.2,
            'rsi_14' => 48.0,
            'sub_signal' => 'ret2d',
        ]);

        $this->assertSame('C', $gradedC['grade']);
        $this->assertLessThan(50, $gradedC['quality_score']);
        $this->assertSame(0, $gradedC['recommended_sizing_pct']);
    }

    public function test_backfill_indicators_command_updates_trades(): void
    {
        $stock = Stock::factory()->create(['code' => 'DEWA']);

        $trade = Trade::create([
            'user_id' => 2,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'direction' => 'long',
            'signal_quality' => 'journal',
            'entry_price' => 450,
            'stop_loss' => 434,
            'target_1' => 472,
            'lot_size' => 1000,
            'quantity' => 1000,
            'position_value' => 450000,
            'status' => 'open',
            'entry_date' => '2026-11-10',
            'result' => 'open',
            'notes' => 'LIVE — sinyal otomatis GABUNGAN, jenis: drawdown',
            'strategy_label' => 'gabungan',
        ]);

        $this->artisan('trades:backfill-indicators')
            ->expectsOutputToContain('Memproses backfill')
            ->expectsOutputToContain('Selesai!')
            ->assertExitCode(0);

        $trade->refresh();
        $this->assertContains($trade->signal_quality, ['A+', 'A', 'B', 'C']);
        $this->assertNotNull($trade->dss_score);
        $this->assertIsArray($trade->indicators_snapshot);
        $this->assertSame('drawdown', $trade->indicators_snapshot['sub_signal']);
    }
}

