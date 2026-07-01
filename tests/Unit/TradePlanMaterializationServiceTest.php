<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionRiskEvaluationService;
use App\Services\Trading\TradePlanMaterializationService;
use Tests\TestCase;

class TradePlanMaterializationServiceTest extends TestCase
{
    public function test_no_candidate_is_unavailable(): void
    {
        $plan = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt()]);

        $this->assertSame('trading_reference_trade_plan_v1', $plan['schema_version']);
        $this->assertSame('unavailable', $plan['status']);
        $this->assertSame('candidate_not_available', $plan['eligibility']);
        $this->assertContains('TRADE_PLAN_CANDIDATE_REQUIRED', $plan['reason_codes']);
        $this->assertNull($plan['entry']['reference_price']);
    }

    public function test_observation_only_candidate_is_unavailable(): void
    {
        $candidate = $this->candidate(false);
        $plan = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate]);

        $this->assertSame('unavailable', $plan['status']);
        $this->assertSame('candidate_not_ready', $plan['eligibility']);
        $this->assertContains('TRADE_PLAN_CANDIDATE_NOT_READY', $plan['reason_codes']);
    }

    public function test_missing_selected_parameters_or_risk_are_unavailable(): void
    {
        $candidate = $this->candidate();
        $withoutParameters = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate]);
        $withoutRisk = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $this->parameters($candidate)]);

        $this->assertSame('selected_parameters_unavailable', $withoutParameters['eligibility']);
        $this->assertContains('TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED', $withoutParameters['reason_codes']);
        $this->assertSame('action_risk_unavailable', $withoutRisk['eligibility']);
        $this->assertContains('TRADE_PLAN_ACTION_RISK_REQUIRED', $withoutRisk['reason_codes']);
    }

    public function test_identity_and_risk_geometry_mismatch_block_materialization(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $risk = $this->risk($candidate, $parameters, $this->entryReference($candidate));
        $parameters['candidate_id'] = 'bad';
        $risk['metrics']['gross_reward_risk_ratio'] = 9.9;

        $plan = (new TradePlanMaterializationService())->materialize([
            'decision_at' => $this->decisionAt(),
            'action_candidate' => $candidate,
            'selected_parameters' => $parameters,
            'action_risk' => $risk,
            'entry_reference' => $this->entryReference($candidate),
        ]);

        $this->assertSame('blocked', $plan['status']);
        $this->assertSame('integrity_blocked', $plan['eligibility']);
        $this->assertContains('TRADE_PLAN_IDENTITY_MISMATCH', $plan['reason_codes']);
        $this->assertContains('TRADE_PLAN_RISK_GEOMETRY_MISMATCH', $plan['reason_codes']);
    }

    public function test_invalid_and_stale_entry_reference_block_plan(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $risk = $this->risk($candidate, $parameters);
        $entry = $this->entryReference($candidate);
        $entry['price'] = 0;
        $invalid = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk, 'entry_reference' => $entry]);

        $entry = $this->entryReference($candidate);
        $entry['observed_at'] = '2026-07-01T07:00:00+07:00';
        $stale = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk, 'entry_reference' => $entry]);

        $this->assertSame('parameter_ready', $invalid['status']);
        $this->assertContains('TRADE_PLAN_ENTRY_REFERENCE_REQUIRED', $invalid['reason_codes']);
        $this->assertSame('parameter_ready', $stale['status']);
        $this->assertContains('TRADE_PLAN_ENTRY_REFERENCE_STALE', $stale['reason_codes']);
    }

    public function test_parameter_ready_without_entry_reference(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $risk = $this->risk($candidate, $parameters);

        $plan = (new TradePlanMaterializationService())->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk]);

        $this->assertSame('parameter_ready', $plan['status']);
        $this->assertSame('entry_reference_unavailable', $plan['eligibility']);
        $this->assertSame(5.0, $plan['take_profit']['percentage']);
        $this->assertSame(2.0, $plan['stop_loss']['percentage']);
        $this->assertSame(2.5, $plan['risk_geometry']['gross_reward_risk_ratio']);
        $this->assertNull($plan['take_profit']['reference_price']);
        $this->assertFalse($plan['execution']['executable']);
    }

    public function test_materialized_reference_prices_are_deterministic_and_non_executable(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $entry = $this->entryReference($candidate);
        $risk = $this->risk($candidate, $parameters, $entry);
        $service = new TradePlanMaterializationService();

        $first = $service->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk, 'entry_reference' => $entry]);
        $second = $service->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk, 'entry_reference' => $entry]);

        $this->assertSame($first, $second);
        $this->assertSame('materialized', $first['status']);
        $this->assertSame(100.0, $first['entry']['reference_price']);
        $this->assertSame(105.0, $first['take_profit']['reference_price']);
        $this->assertSame(98.0, $first['stop_loss']['reference_price']);
        $this->assertSame(5.0, $first['risk_geometry']['gross_profit_per_unit']);
        $this->assertSame(2.0, $first['risk_geometry']['gross_loss_per_unit']);
        $this->assertSame('not_executable', $first['execution']['status']);
        $this->assertNull($first['execution']['quantity']);
        $this->assertSame('not_implemented', $first['holding']['status']);
        $this->assertSame('not_implemented', $first['reentry']['status']);
    }

    public function test_validator_rejects_executable_payload(): void
    {
        $candidate = $this->candidate();
        $parameters = $this->parameters($candidate);
        $entry = $this->entryReference($candidate);
        $risk = $this->risk($candidate, $parameters, $entry);
        $service = new TradePlanMaterializationService();
        $plan = $service->materialize(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'action_risk' => $risk, 'entry_reference' => $entry]);
        $plan['execution']['quantity'] = 1;

        $this->expectException(\InvalidArgumentException::class);
        $service->validateReferencePlan($plan);
    }

    protected function risk(array $candidate, array $parameters, ?array $entry = null): array
    {
        return (new ActionRiskEvaluationService())->evaluate(['decision_at' => $this->decisionAt(), 'action_candidate' => $candidate, 'selected_parameters' => $parameters, 'entry_reference' => $entry]);
    }

    protected function candidate(bool $ready = true): array
    {
        return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact($ready),'sl_optimizer'=>$this->artifact($ready)],'evidence_readiness'=>$ready ? 'decision_ready' : 'research_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']);
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

    protected function decisionAt(): string
    {
        return '2026-07-01T10:00:00+07:00';
    }
}
