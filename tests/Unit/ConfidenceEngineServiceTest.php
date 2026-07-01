<?php

namespace Tests\Unit;

use App\Services\Trading\ConfidenceEngineService;
use Tests\TestCase;

class ConfidenceEngineServiceTest extends TestCase
{
    public function test_research_ready_evidence_confidence_and_action_null(): void
    {
        $confidence = (new ConfidenceEngineService())->calculate($this->context());
        $this->assertSame('trading_confidence_v1_1', $confidence['schema_version']);
        $this->assertSame('research_only', $confidence['status']);
        $this->assertIsFloat($confidence['evidence_confidence']['score']);
        $this->assertNull($confidence['trade_action_confidence']['score']);
        $this->assertSame('unavailable', $confidence['trade_action_confidence']['status']);
        $this->assertSame('available', $confidence['safety_decision_confidence']['status']);
        $this->assertNotEmpty($confidence['evidence_confidence']['components']);
    }

    public function test_probability_magnitude_does_not_change_confidence(): void
    {
        $engine = new ConfidenceEngineService();
        $a = $this->context();
        $b = $this->context();
        $a['prediction_snapshots'][0]['probability'] = 0.70;
        $b['prediction_snapshots'][0]['probability'] = 0.95;
        $this->assertSame($engine->calculate($a)['evidence_confidence']['score'], $engine->calculate($b)['evidence_confidence']['score']);
    }

    public function test_decision_ready_trade_action_confidence_still_requires_candidate(): void
    {
        $ctx = $this->context('decision_ready', 'eligible_but_not_supported');
        $confidence = (new ConfidenceEngineService())->calculate($ctx);
        $this->assertSame('decision_ready', $confidence['status']);
        $this->assertSame('unavailable', $confidence['trade_action_confidence']['status']);
        $this->assertNull($confidence['trade_action_confidence']['score']);
        $this->assertSame('action_candidate_not_available', $confidence['trade_action_confidence']['eligibility']);
        $this->assertNotContains('implementation_capability', array_column($confidence['evidence_confidence']['components'], 'key'));
    }

    public function test_caps_penalties_and_invalid_config(): void
    {
        $confidence = (new ConfidenceEngineService())->calculate($this->context());
        $this->assertNotEmpty($confidence['evidence_confidence']['penalties']);
        $this->assertTrue(collect($confidence['evidence_confidence']['caps'])->firstWhere('code', 'RESEARCH_ONLY_ACTION_CAP')['applied']);
        $this->expectException(\InvalidArgumentException::class);
        new ConfidenceEngineService(array_replace_recursive(config('trading_confidence'), ['component_weights' => ['bad' => -1]]));
    }

    protected function context(string $readiness = 'research_ready', string $eligibility = 'blocked'): array
    {
        return [
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'prediction_snapshots' => [['semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','probability'=>0.7]],
            'prediction_evidence' => ['quality_status'=>'available','directional_available'=>true,'regime_available'=>false,'conflict_status'=>'none'],
            'artifact_availability' => [
                'tp_optimizer' => ['latest_research_available'=>true,'quality_grade'=>'warning','is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>[]],
                'sl_optimizer' => ['latest_research_available'=>true,'quality_grade'=>'limited','is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>[]],
            ],
            'evidence_readiness' => $readiness,
            'capability_readiness' => 'basic_only',
            'action_eligibility' => $eligibility,
            'reason_codes' => ['NO_DECISION_USABLE_TP','NO_DECISION_USABLE_SL','SELECTED_TP_UNAVAILABLE','ATR_FAMILY_UNAVAILABLE'],
        ];
    }
}
