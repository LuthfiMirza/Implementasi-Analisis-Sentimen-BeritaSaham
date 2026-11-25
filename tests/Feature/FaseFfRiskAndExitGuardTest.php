<?php

namespace Tests\Feature;

use App\Services\Trading\TradeQualityGraderService;
use Tests\TestCase;

class FaseFfRiskAndExitGuardTest extends TestCase
{
    public function test_grade_sizing_follows_ff1_walk_forward_oos_tiers(): void
    {
        $grader = app(TradeQualityGraderService::class);

        // Grade A+ -> 125% (OOS PF 4.74)
        $aPlus = $grader->gradeTrade('DEWA', 'gabungan', [
            'vol_ratio_ma20' => 1.5,
            'lower_wick_pct' => 1.8,
            'rsi_14' => 35.0,
            'sub_signal' => 'drawdown',
        ]);
        $this->assertSame('A+', $aPlus['grade']);
        $this->assertSame(125, $aPlus['recommended_sizing_pct']);

        // Grade A -> 100%
        $a = $grader->gradeTrade('PTRO', 'gabungan', [
            'vol_ratio_ma20' => 0.9,
            'lower_wick_pct' => 1.4,
            'rsi_14' => 45.0,
            'sub_signal' => 'drawdown',
        ]);
        $this->assertSame('A', $a['grade']);
        $this->assertSame(100, $a['recommended_sizing_pct']);

        // Grade B -> 50% (score 50-64)
        $b = $grader->gradeTrade('INET', 'gabungan', [
            'vol_ratio_ma20' => 0.8,
            'lower_wick_pct' => 0.7,
            'rsi_14' => 45.0,
            'sub_signal' => 'gabungan',
        ]);
        $this->assertSame('B', $b['grade']);
        $this->assertSame(50, $b['recommended_sizing_pct']);

        // Grade C (Dead Low) -> 0%
        $c = $grader->gradeTrade('BRPT', 'gabungan', [
            'vol_ratio_ma20' => 1.4,
            'lower_wick_pct' => 0.0,
            'rsi_14' => 31.0,
            'sub_signal' => 'drawdown',
        ]);
        $this->assertSame('C', $c['grade']);
        $this->assertSame(0, $c['recommended_sizing_pct']);
    }

    public function test_conglomerate_cluster_cap_detects_bakrie_and_barito_conflicts(): void
    {
        $grader = app(TradeQualityGraderService::class);

        $conflict = $grader->checkClusterConflict('ENRG', ['BUMI', 'SMGR']);
        $this->assertSame('BAKRIE', $conflict['cluster']);
        $this->assertTrue($conflict['conflict']);
        $this->assertSame(['BUMI'], $conflict['open_cluster_tickers']);
        $this->assertStringContainsString('BAKRIE', (string) $conflict['warning']);

        // Same ticker already open is not a cross-peer cluster conflict
        $sameTicker = $grader->checkClusterConflict('BUMI', ['BUMI']);
        $this->assertFalse($sameTicker['conflict']);

        // Unclustered ticker has no conflict
        $unclustered = $grader->checkClusterConflict('UNVR', ['BUMI', 'BRPT']);
        $this->assertNull($unclustered['cluster']);
        $this->assertFalse($unclustered['conflict']);
    }

    public function test_fh1_microstructure_late_volume_and_vwap_adjust_score(): void
    {
        $grader = app(TradeQualityGraderService::class);

        $strongLate = $grader->gradeTrade('ENRG', 'gabungan', [
            'vol_ratio_ma20' => 0.9,
            'lower_wick_pct' => 1.5,
            'rsi_14' => 45.0,
            'late_vol_ratio' => 38.0,
            'close_vs_vwap_pct' => 0.8,
        ]);

        $dryLate = $grader->gradeTrade('ENRG', 'gabungan', [
            'vol_ratio_ma20' => 0.9,
            'lower_wick_pct' => 1.5,
            'rsi_14' => 45.0,
            'late_vol_ratio' => 11.0,
            'close_vs_vwap_pct' => -2.0,
        ]);

        $this->assertSame('STRONG_LATE_ABSORPTION (>=30%)', $strongLate['snapshot']['microstructure_zone']);
        $this->assertSame('DRY_LATE_TRAP (<15%)', $dryLate['snapshot']['microstructure_zone']);
        $this->assertGreaterThan($dryLate['quality_score'], $strongLate['quality_score']);
        $this->assertGreaterThanOrEqual(30, $strongLate['quality_score'] - $dryLate['quality_score']);
    }
}
