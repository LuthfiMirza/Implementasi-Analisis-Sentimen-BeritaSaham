<?php

namespace Tests\Unit;

use App\Services\Trading\ConfidenceEngineService;
use App\Services\Trading\ReasonEngineService;
use Tests\TestCase;

class ReasonEngineServiceTest extends TestCase
{
    public function test_structured_reasons_ordering_summary_and_no_filler(): void
    {
        $confidence = (new ConfidenceEngineService())->calculate($this->context());
        $result = (new ReasonEngineService())->build(['base_reasons' => $this->baseReasons(), 'confidence' => $confidence]);
        $this->assertSame('trading_reason_v1_1', $result['schema_version']);
        $this->assertGreaterThan(0, $result['summary']['blocking_count']);
        $this->assertNotNull($result['summary']['dominant_blocker']);
        $this->assertSame($result['reasons'][0]['severity'], 'blocking');
        foreach ($result['reasons'] as $reason) {
            $this->assertArrayHasKey('source', $reason);
            $this->assertStringNotContainsString('buy now', strtolower($reason['message']));
            $this->assertStringNotContainsString('strong buy', strtolower($reason['message']));
        }
    }

    public function test_deduplication_and_supportive_does_not_remove_blocker(): void
    {
        $confidence = (new ConfidenceEngineService())->calculate($this->context());
        $reasons = $this->baseReasons();
        $reasons[] = $reasons[0];
        $reasons[] = ['code'=>'DIRECTIONAL_PREDICTION_AVAILABLE','category'=>'prediction','severity'=>'supportive','message'=>'Directional prediction available.','source'=>[]];
        $result = (new ReasonEngineService())->build(['base_reasons'=>$reasons,'confidence'=>$confidence]);
        $codes = array_column($result['reasons'], 'code');
        $this->assertSame(count($codes), count(array_unique($codes)));
        $this->assertContains('NO_DECISION_USABLE_TP', $codes);
        $this->assertContains('DIRECTIONAL_PREDICTION_AVAILABLE', $codes);
        $this->assertSame(1, $result['summary']['supportive_count']);
    }

    public function test_source_aggregation_and_dominant_blocker_priority(): void
    {
        $confidence = (new ConfidenceEngineService())->calculate($this->context());
        $reasons = $this->baseReasons();
        $reasons[] = ['code'=>'RESEARCH_ONLY_EVIDENCE','category'=>'artifact_usability','severity'=>'warning','message'=>'Research-only evidence.','source'=>['artifact_type'=>'tp_optimizer','artifact_id'=>1,'schema_version'=>'tp_optimizer_v1']];
        $reasons[] = ['code'=>'RESEARCH_ONLY_EVIDENCE','category'=>'artifact_usability','severity'=>'warning','message'=>'Research-only evidence.','source'=>['artifact_type'=>'sl_optimizer','artifact_id'=>2,'schema_version'=>'sl_optimizer_v1']];
        $reasons[] = ['code'=>'NO_DECISION_USABLE_SL','category'=>'artifact_usability','severity'=>'blocking','message'=>'SL research is available but not decision-usable.','source'=>['artifact_type'=>'sl_optimizer','artifact_id'=>2,'schema_version'=>'sl_optimizer_v1']];

        $result = (new ReasonEngineService())->build(['base_reasons'=>$reasons,'confidence'=>$confidence]);
        $researchOnly = collect($result['reasons'])->firstWhere('code', 'RESEARCH_ONLY_EVIDENCE');

        $this->assertSame(2, $researchOnly['source_count']);
        $this->assertCount(2, $researchOnly['sources']);
        $this->assertSame('NO_DECISION_USABLE_SL', $result['summary']['dominant_blocker']);
    }

    protected function baseReasons(): array
    {
        return [
            ['code'=>'NO_DECISION_USABLE_TP','category'=>'artifact_usability','severity'=>'blocking','message'=>'TP research is available but not decision-usable.','source'=>['artifact_type'=>'tp_optimizer','artifact_id'=>1,'schema_version'=>'tp_optimizer_v1']],
            ['code'=>'HIGH_UNCLASSIFIED_RATE','category'=>'artifact_quality','severity'=>'warning','message'=>'High unclassified rate.','source'=>['artifact_type'=>'reentry_research','artifact_id'=>2,'schema_version'=>'reentry_research_v1_1']],
        ];
    }

    protected function context(): array
    {
        return [
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'prediction_snapshots' => [['semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','probability'=>0.7]],
            'prediction_evidence' => ['quality_status'=>'available','directional_available'=>true,'regime_available'=>false,'conflict_status'=>'none'],
            'artifact_availability' => ['tp_optimizer' => ['latest_research_available'=>true,'quality_grade'=>'warning','is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>[]]],
            'evidence_readiness' => 'research_ready',
            'capability_readiness' => 'basic_only',
            'action_eligibility' => 'blocked',
            'reason_codes' => ['NO_DECISION_USABLE_TP','HIGH_UNCLASSIFIED_RATE'],
        ];
    }
}
