<?php

namespace Tests\Unit;

use App\Services\Trading\RiskEngineService;
use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\TradePlanService;
use Tests\TestCase;

class RiskEngineServiceTest extends TestCase
{
    public function test_research_risk_available_and_decision_risk_unavailable(): void
    {
        $risk = (new RiskEngineService())->assess($this->context());

        $this->assertSame('trading_risk_v1_3', $risk['schema_version']);
        $this->assertSame('research_only', $risk['research_risk_evidence']['status']);
        $this->assertSame('trading_action_risk_v1', $risk['action_specific_risk']['schema_version']);
        $this->assertSame('unavailable', $risk['action_specific_risk']['status']);
        $this->assertSame('unavailable', $risk['decision_risk']['status']);
        $this->assertSame('candidate_not_available', $risk['decision_risk']['eligibility']);
        $this->assertNull($risk['decision_risk']['action']);
        $this->assertNull($risk['decision_risk']['risk_reward_ratio']);
        $this->assertSame('unavailable', $risk['capital_risk']['status']);
        $this->assertSame('unavailable', $risk['position_sizing']['status']);
        $this->assertSame('trading_portfolio_risk_v1', $risk['portfolio_risk']['schema_version']);
        $this->assertSame('unavailable', $risk['portfolio_risk']['status']);
        $this->assertNull($risk['position_sizing']['metrics']['executable_quantity']);
        $this->assertContains('RESEARCH_RISK_EVIDENCE_AVAILABLE', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_CANDIDATE_REQUIRED', $risk['reason_codes']);
    }

    public function test_partial_stale_quarantined_dependency_and_selected_missing(): void
    {
        $ctx = $this->context();
        unset($ctx['artifact_availability']['reentry_research']);
        $ctx['artifact_availability']['sl_optimizer']['quality_grade'] = 'limited';
        $ctx['artifact_availability']['sl_optimizer']['is_stale'] = true;
        $ctx['artifact_availability']['tp_optimizer']['is_quarantined'] = true;
        $ctx['artifact_availability']['tp_optimizer']['dependency_status'] = ['checksum_mismatch'];
        $risk = (new RiskEngineService())->assess($ctx);

        $this->assertSame('invalid', $risk['research_risk_evidence']['status']);
        $this->assertContains('RISK_ARTIFACT_STALE', $risk['reason_codes']);
        $this->assertContains('RISK_ARTIFACT_QUARANTINED', $risk['reason_codes']);
        $this->assertContains('RISK_DEPENDENCY_UNRESOLVED', $risk['reason_codes']);
        $this->assertContains('ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED', $risk['reason_codes']);
    }

    public function test_action_identity_required_and_no_numeric_placeholder(): void
    {
        $ctx = $this->context();
        $ctx['action_candidate'] = ['schema_version'=>'trading_action_candidate_v1','status'=>'candidate_ready','candidate_id'=>null,'intent'=>null,'candidate_version' => 'synthetic_action_candidate_v1'];
        $risk = (new RiskEngineService())->assess($ctx);

        $this->assertContains('ACTION_RISK_UNSUPPORTED_INTENT', $risk['reason_codes']);
        $this->assertNull($risk['decision_risk']['entry_price']);
        $this->assertNull($risk['decision_risk']['take_profit']);
        $this->assertNull($risk['decision_risk']['stop_loss']);
    }

    public function test_synthetic_valid_action_risk_is_evaluated(): void
    {
        $candidate = $this->candidate();
        $ctx = $this->context();
        $ctx['action_candidate'] = $candidate;
        $ctx['selected_parameters'] = $this->parameters($candidate);
        $risk = (new RiskEngineService())->assess($ctx);

        $this->assertSame('evaluated', $risk['action_specific_risk']['status']);
        $this->assertSame(2.5, $risk['action_specific_risk']['metrics']['gross_reward_risk_ratio']);
        $this->assertSame('unavailable', $risk['decision_risk']['status']);
        $this->assertNull($risk['decision_risk']['risk_reward_ratio']);
        $this->assertSame('unavailable', $risk['capital_risk']['status']);
        $this->assertSame('unavailable', $risk['position_sizing']['status']);
    }

    public function test_synthetic_capital_risk_and_position_sizing_are_reference_only(): void
    {
        $candidate = $this->candidate();
        $ctx = $this->context();
        $ctx['action_candidate'] = $candidate;
        $ctx['selected_parameters'] = $this->parameters($candidate);
        $ctx['entry_reference'] = $this->entryReference($candidate);
        $first = (new RiskEngineService())->assess($ctx);
        $referencePlan = (new TradePlanService())->build(['decision_at'=>$ctx['decision_at'],'risk'=>$first,'action_candidate'=>$candidate,'selected_parameters'=>$ctx['selected_parameters'],'entry_reference'=>$ctx['entry_reference']])['reference_plan'];
        $ctx['reference_plan'] = $referencePlan;
        $ctx['capital_context'] = $this->capitalContext();
        $ctx['capital_risk_policy'] = $this->capitalPolicy($candidate);
        $risk = (new RiskEngineService())->assess($ctx);

        $this->assertSame('evaluated_reference', $risk['capital_risk']['status']);
        $this->assertSame(1000000.0, $risk['capital_risk']['metrics']['capital_base']);
        $this->assertSame(10000.0, $risk['capital_risk']['metrics']['maximum_loss_amount']);
        $this->assertSame('reference_sized', $risk['position_sizing']['status']);
        $this->assertSame(5000.0, $risk['position_sizing']['metrics']['raw_reference_units']);
        $this->assertSame(5000.0, $risk['position_sizing']['metrics']['whole_unit_reference_floor']);
        $this->assertSame(500000.0, $risk['position_sizing']['metrics']['reference_notional']);
        $this->assertNull($risk['position_sizing']['metrics']['executable_quantity']);
        $this->assertSame('unavailable', $risk['portfolio_risk']['status']);
    }

    public function test_config_and_schema_validation(): void
    {
        $engine = new RiskEngineService();
        $risk = $engine->assess($this->context());
        $risk['decision_risk']['risk_reward_ratio'] = 0;
        $this->expectException(\InvalidArgumentException::class);
        $engine->validateRisk($risk);
    }

    public function test_invalid_config_is_rejected(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        new RiskEngineService(array_replace(config('trading_risk'), ['research_risk_required_artifacts' => ['unknown_artifact']]));
    }

    protected function context(): array
    {
        return [
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'artifact_availability' => [
                'tp_optimizer' => $this->artifact('tp_optimizer', false, true),
                'sl_optimizer' => $this->artifact('sl_optimizer', false, true),
                'reentry_research' => $this->artifact('reentry_research', false, true, ['high_unclassified_rate', 'ATR family unavailable', 'extreme_winner_dependency']),
            ],
            'confidence' => [],
            'action_candidate' => null,
        ];
    }

    protected function artifact(string $type, bool $decision, bool $valid, array $warnings = []): array
    {
        return [
            'latest_valid_available' => $valid,
            'latest_research_available' => $valid,
            'latest_decision_available' => $decision,
            'latest_valid' => ['id' => 1, 'schema_version' => $type.'_v1', 'usage_tier' => $decision ? 'decision_usable' : 'research_only'],
            'quality_grade' => 'warning',
            'selected_available' => $decision,
            'is_stale' => false,
            'is_quarantined' => false,
            'dependency_status' => ['resolved'],
            'warnings' => $warnings,
        ];
    }

    protected function candidate(): array
    {
        return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->candidateArtifact(true),'sl_optimizer'=>$this->candidateArtifact(true)],'evidence_readiness'=>'decision_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']);
    }

    protected function parameters(array $candidate): array
    {
        $source = fn($type, $id) => ['registry_artifact_id'=>$id,'artifact_type'=>$type,'schema_version'=>$type.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']];
        return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$source('tp_optimizer', 101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$source('sl_optimizer', 102)],'synthetic_test_only'=>true];
    }

    protected function candidateArtifact(bool $decision): array
    {
        return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function entryReference(array $candidate): array
    {
        return ['schema_version'=>'trading_entry_reference_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'fixture-entry-100'],'executable'=>false,'synthetic_test_only'=>true];
    }

    protected function capitalContext(): array
    {
        return ['schema_version'=>'trading_capital_context_v1','status'=>'reference_only','capital_scope'=>'single_candidate_reference','capital_base'=>['amount'=>1000000.0,'currency'=>'IDR'],'available_cash'=>null,'reserved_capital'=>null,'current_exposure'=>null,'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'capital-fixture-1m'],'approved_for_execution'=>false,'synthetic_test_only'=>true,'warnings'=>[]];
    }

    protected function capitalPolicy(array $candidate): array
    {
        return ['schema_version'=>'trading_capital_risk_policy_v1','status'=>'reference_only','method'=>'fixed_fractional','maximum_loss_pct'=>1.0,'maximum_loss_amount'=>null,'currency'=>'IDR','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'policy_version'=>'fixed_fractional_reference_v1','source'=>['type'=>'synthetic_test_fixture','identifier'=>'risk-policy-1pct'],'approved_for_execution'=>false,'synthetic_test_only'=>true,'warnings'=>[]];
    }
}
