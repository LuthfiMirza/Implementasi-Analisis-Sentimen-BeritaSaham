<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionRiskEvaluationService;
use Tests\TestCase;

class ActionRiskEvaluationServiceTest extends TestCase
{
    public function test_no_candidate_and_observation_candidate_are_unavailable(): void
    {
        $service = new ActionRiskEvaluationService();
        $none = $service->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00']);
        $this->assertSame('unavailable', $none['status']);
        $this->assertContains('ACTION_RISK_CANDIDATE_REQUIRED', $none['reason_codes']);
        $this->assertNull($none['metrics']['gross_reward_risk_ratio']);

        $obs = $service->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$this->candidate('research_ready')]);
        $this->assertSame('unavailable', $obs['status']);
        $this->assertContains('ACTION_RISK_CANDIDATE_NOT_READY', $obs['reason_codes']);
    }

    public function test_parameter_validation_blocks_research_only_and_identity_mismatch(): void
    {
        $candidate = $this->candidate('decision_ready');
        $params = $this->parameters($candidate);
        $params['candidate_id'] = 'bad';
        $params['take_profit']['source_artifact']['usage_tier'] = 'research_only';
        $risk = (new ActionRiskEvaluationService())->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$params]);

        $this->assertSame('blocked', $risk['status']);
        $this->assertContains('ACTION_RISK_IDENTITY_MISMATCH', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_PARAMETER_EVIDENCE_RESEARCH_ONLY', $risk['reason_codes']);
    }

    public function test_invalid_sources_and_parameters_are_rejected(): void
    {
        $candidate = $this->candidate('decision_ready');
        $params = $this->parameters($candidate);
        $params['stop_loss']['value'] = 0;
        $params['stop_loss']['source_artifact']['stale'] = true;
        $params['take_profit']['source_artifact']['dependency_status'] = ['checksum_mismatch'];
        $params['take_profit']['parameter_type'] = 'atr_multiple';
        $risk = (new ActionRiskEvaluationService())->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$params]);

        $this->assertContains('ACTION_RISK_SOURCE_STALE', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_DEPENDENCY_UNRESOLVED', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_PARAMETER_TYPE_UNSUPPORTED', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_PARAMETER_INVALID', $risk['reason_codes']);
    }

    public function test_valid_percentage_geometry_is_deterministic(): void
    {
        $candidate = $this->candidate('decision_ready');
        $params = $this->parameters($candidate);
        $service = new ActionRiskEvaluationService();
        $first = $service->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$params]);
        $second = $service->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$params]);

        $this->assertSame($first, $second);
        $this->assertSame('evaluated', $first['status']);
        $this->assertSame(5.0, $first['metrics']['gross_upside_pct']);
        $this->assertSame(2.0, $first['metrics']['gross_downside_pct']);
        $this->assertSame(2.5, $first['metrics']['gross_reward_risk_ratio']);
        $this->assertNull($first['metrics']['probability_of_profit']);
        $this->assertNull($first['metrics']['expected_value_pct']);
        $this->assertNull($first['metrics']['net_reward_risk_ratio']);
        $this->assertContains('ACTION_RISK_GROSS_GEOMETRY_AVAILABLE', $first['reason_codes']);
    }

    public function test_entry_reference_geometry_is_non_executable(): void
    {
        $candidate = $this->candidate('decision_ready');
        $risk = (new ActionRiskEvaluationService())->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$this->parameters($candidate),'entry_reference'=>['price'=>100,'source'=>'synthetic_test']]);

        $this->assertSame(100.0, $risk['metrics']['entry_price']);
        $this->assertSame(105.0, $risk['metrics']['take_profit_price']);
        $this->assertSame(98.0, $risk['metrics']['stop_loss_price']);
        $this->assertSame(5.0, $risk['metrics']['gross_profit_per_unit']);
        $this->assertSame(2.0, $risk['metrics']['gross_loss_per_unit']);
        $this->assertContains('ACTION_RISK_NON_EXECUTABLE_REFERENCE', $risk['reason_codes']);
        $this->assertTrue($risk['metadata']['non_executable']);
    }

    public function test_validation_rejects_probability_metric(): void
    {
        $candidate = $this->candidate('decision_ready');
        $risk = (new ActionRiskEvaluationService())->evaluate(['decision_at'=>'2026-07-01T10:00:00+07:00','action_candidate'=>$candidate,'selected_parameters'=>$this->parameters($candidate)]);
        $risk['metrics']['probability_of_profit'] = 0.7;
        $this->expectException(\InvalidArgumentException::class);
        (new ActionRiskEvaluationService())->validateActionRisk($risk);
    }

    protected function candidate(string $readiness): array
    {
        return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact(true),'sl_optimizer'=>$this->artifact(true)],'evidence_readiness'=>$readiness,'position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']);
    }

    protected function parameters(array $candidate): array
    {
        return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->source('tp_optimizer', 101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->source('sl_optimizer', 102)],'generated_at'=>'2026-07-01T09:55:00+07:00','warnings'=>[],'synthetic_test_only'=>true];
    }

    protected function source(string $type, int $id): array
    {
        return ['registry_artifact_id'=>$id,'artifact_type'=>$type,'schema_version'=>$type.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function artifact(bool $decision): array
    {
        return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }
}
