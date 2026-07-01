<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionRiskEvaluationService;
use App\Services\Trading\RiskEngineService;
use App\Services\Trading\TradePlanService;
use Tests\TestCase;

class TradePlanServiceTest extends TestCase
{
    public function test_plan_unavailable_without_action_candidate_and_decision_risk(): void
    {
        $risk = (new RiskEngineService())->assess($this->riskContext());
        $plan = (new TradePlanService())->build(['risk' => $risk, 'action_candidate' => null, 'position_context' => 'no_open_trade']);

        $this->assertSame('trading_trade_plan_v1_1', $plan['schema_version']);
        $this->assertSame('unavailable', $plan['status']);
        $this->assertSame('candidate_not_available', $plan['eligibility']);
        $this->assertSame('trading_reference_trade_plan_v1', $plan['reference_plan']['schema_version']);
        $this->assertSame('unavailable', $plan['reference_plan']['status']);
        $this->assertNull($plan['entry']['price']);
        $this->assertNull($plan['take_profit']['price']);
        $this->assertNull($plan['stop_loss']['price']);
        $this->assertFalse($plan['execution_readiness']['executable']);
        $this->assertFalse($plan['reentry']['enabled']);
        $this->assertSame(0, $plan['reentry']['maximum_reentries']);
        $this->assertContains('TRADE_PLAN_REFERENCE_UNAVAILABLE', $plan['reason_codes']);
    }

    public function test_open_trade_does_not_produce_hold_plan(): void
    {
        $risk = (new RiskEngineService())->assess($this->riskContext());
        $plan = (new TradePlanService())->build(['risk' => $risk, 'action_candidate' => null, 'position_context' => 'open_trade']);

        $this->assertNull($plan['action']);
        $this->assertContains('TRADE_PLAN_POSITION_MANAGEMENT_NOT_IMPLEMENTED', $plan['reason_codes']);
        $this->assertNotSame('HOLD', $plan['action']);
    }

    public function test_invalid_executable_parameter_rejected_when_unavailable(): void
    {
        $risk = (new RiskEngineService())->assess($this->riskContext());
        $service = new TradePlanService();
        $plan = $service->build(['risk' => $risk, 'action_candidate' => null, 'position_context' => 'no_open_trade']);
        $plan['take_profit']['price'] = 110;

        $this->expectException(\InvalidArgumentException::class);
        $service->validateTradePlan($plan);
    }

    public function test_synthetic_parameter_ready_without_entry_reference(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $risk = (new ActionRiskEvaluationService())->evaluate([
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'action_candidate' => $candidate,
            'selected_parameters' => $parameters,
        ]);

        $plan = (new TradePlanService())->build([
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'action_candidate' => $candidate,
            'selected_parameters' => $parameters,
            'risk' => ['action_specific_risk' => $risk],
        ]);

        $this->assertSame('parameter_ready', $plan['status']);
        $this->assertSame('parameter_ready', $plan['reference_plan']['status']);
        $this->assertSame('entry_reference_unavailable', $plan['reference_plan']['eligibility']);
        $this->assertSame(5.0, $plan['reference_plan']['take_profit']['percentage']);
        $this->assertSame(2.0, $plan['reference_plan']['stop_loss']['percentage']);
        $this->assertSame(2.5, $plan['reference_plan']['risk_geometry']['gross_reward_risk_ratio']);
        $this->assertNull($plan['reference_plan']['take_profit']['reference_price']);
        $this->assertSame('unavailable', $plan['execution_readiness']['status']);
        $this->assertNull($plan['position_sizing']['quantity']);
    }

    public function test_synthetic_materialized_reference_plan_is_non_executable(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $entry = $this->entryReference($candidate);
        $risk = (new ActionRiskEvaluationService())->evaluate([
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'action_candidate' => $candidate,
            'selected_parameters' => $parameters,
            'entry_reference' => $entry,
        ]);

        $plan = (new TradePlanService())->build([
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'action_candidate' => $candidate,
            'selected_parameters' => $parameters,
            'entry_reference' => $entry,
            'risk' => ['action_specific_risk' => $risk],
        ]);

        $this->assertSame('materialized', $plan['status']);
        $this->assertSame('materialized', $plan['reference_plan']['status']);
        $this->assertSame(100.0, $plan['reference_plan']['entry']['reference_price']);
        $this->assertSame(105.0, $plan['reference_plan']['take_profit']['reference_price']);
        $this->assertSame(98.0, $plan['reference_plan']['stop_loss']['reference_price']);
        $this->assertSame(5.0, $plan['reference_plan']['risk_geometry']['gross_profit_per_unit']);
        $this->assertSame(2.0, $plan['reference_plan']['risk_geometry']['gross_loss_per_unit']);
        $this->assertSame('reference_ready', $plan['execution_readiness']['status']);
        $this->assertFalse($plan['execution_readiness']['executable']);
        $this->assertNull($plan['position_sizing']['quantity']);
    }

    protected function riskContext(): array
    {
        $artifact = fn ($type) => ['latest_valid_available'=>true,'latest_research_available'=>true,'latest_decision_available'=>false,'latest_valid'=>['id'=>1,'schema_version'=>$type.'_v1','usage_tier'=>'research_only'],'quality_grade'=>'warning','selected_available'=>false,'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved'],'warnings'=>[]];
        return ['decision_at'=>'2026-07-01T10:00:00+07:00','artifact_availability'=>['tp_optimizer'=>$artifact('tp_optimizer'),'sl_optimizer'=>$artifact('sl_optimizer'),'reentry_research'=>$artifact('reentry_research')],'action_candidate'=>null];
    }

    protected function candidate(): array
    {
        return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact(true),'sl_optimizer'=>$this->artifact(true)],'evidence_readiness'=>'decision_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']);
    }

    protected function parameters(array $candidate): array
    {
        return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->source('tp_optimizer',101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->source('sl_optimizer',102)],'generated_at'=>'2026-07-01T09:55:00+07:00','synthetic_test_only'=>true];
    }

    protected function source(string $type, int $id): array
    {
        return ['registry_artifact_id'=>$id,'artifact_type'=>$type,'schema_version'=>$type.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function artifact(bool $decision): array
    {
        return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function entryReference(array $candidate): array
    {
        return ['schema_version'=>'trading_entry_reference_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'fixture-entry-100'],'executable'=>false,'synthetic_test_only'=>true];
    }
}
