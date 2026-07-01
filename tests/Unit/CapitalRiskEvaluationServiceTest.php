<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionRiskEvaluationService;
use App\Services\Trading\CapitalRiskEvaluationService;
use App\Services\Trading\TradePlanService;
use Tests\TestCase;

class CapitalRiskEvaluationServiceTest extends TestCase
{
    public function test_missing_inputs_are_unavailable(): void
    {
        $risk = (new CapitalRiskEvaluationService())->evaluate(['decision_at'=>$this->decisionAt()]);
        $this->assertSame('trading_capital_risk_v1', $risk['schema_version']);
        $this->assertSame('unavailable', $risk['status']);
        $this->assertSame('candidate_not_available', $risk['eligibility']);
        $this->assertContains('CAPITAL_CONTEXT_UNAVAILABLE', $risk['reason_codes']);
    }

    public function test_invalid_context_policy_identity_currency_and_missing_loss_block(): void
    {
        $candidate = $this->candidate();
        $actionRisk = $this->actionRisk($candidate, null);
        $actionRisk['metrics']['gross_loss_per_unit'] = null;
        $context = $this->baseContext($candidate, $actionRisk);
        $context['capital_context']['capital_base']['amount'] = -1;
        $context['capital_risk_policy']['candidate_id'] = 'bad';
        $context['capital_risk_policy']['currency'] = 'USD';
        $risk = (new CapitalRiskEvaluationService())->evaluate($context);

        $this->assertSame('unavailable', $risk['status']);
        $this->assertContains('CAPITAL_CONTEXT_INVALID', $risk['reason_codes']);
        $this->assertContains('CAPITAL_RISK_IDENTITY_MISMATCH', $risk['reason_codes']);
        $this->assertContains('CAPITAL_RISK_CURRENCY_MISMATCH', $risk['reason_codes']);
        $this->assertContains('GROSS_LOSS_PER_UNIT_REQUIRED', $risk['reason_codes']);
    }

    public function test_valid_percentage_budget_is_deterministic_and_non_executable(): void
    {
        $candidate = $this->candidate();
        $context = $this->baseContext($candidate);
        $service = new CapitalRiskEvaluationService();
        $first = $service->evaluate($context);
        $second = $service->evaluate($context);

        $this->assertSame($first, $second);
        $this->assertSame('evaluated_reference', $first['status']);
        $this->assertSame(1000000.0, $first['metrics']['capital_base']);
        $this->assertSame(1.0, $first['metrics']['maximum_loss_pct']);
        $this->assertSame(10000.0, $first['metrics']['maximum_loss_amount']);
        $this->assertSame(2.0, $first['metrics']['gross_loss_per_unit']);
        $this->assertNull($first['metrics']['net_capital_at_risk']);
        $this->assertNull($first['metrics']['portfolio_exposure_after_entry']);
        $this->assertTrue($first['metadata']['non_executable']);
    }

    public function test_explicit_amount_mode_and_inconsistent_dual_mode(): void
    {
        $candidate = $this->candidate();
        $context = $this->baseContext($candidate);
        $context['capital_risk_policy']['maximum_loss_pct'] = null;
        $context['capital_risk_policy']['maximum_loss_amount'] = 7500.0;
        $amount = (new CapitalRiskEvaluationService())->evaluate($context);
        $this->assertSame(7500.0, $amount['metrics']['maximum_loss_amount']);

        $context = $this->baseContext($candidate);
        $context['capital_risk_policy']['maximum_loss_amount'] = 9999.0;
        $invalid = (new CapitalRiskEvaluationService())->evaluate($context);
        $this->assertSame('unavailable', $invalid['status']);
        $this->assertContains('CAPITAL_RISK_POLICY_INVALID', $invalid['reason_codes']);
    }

    protected function baseContext(array $candidate, ?array $actionRisk = null): array
    {
        $actionRisk ??= $this->actionRisk($candidate, $this->entryReference($candidate));
        return ['decision_at'=>$this->decisionAt(),'action_candidate'=>$candidate,'action_risk'=>$actionRisk,'reference_plan'=>$this->referencePlan($candidate),'capital_context'=>$this->capitalContext(),'capital_risk_policy'=>$this->capitalPolicy($candidate)];
    }

    protected function candidate(): array { return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact(true),'sl_optimizer'=>$this->artifact(true)],'evidence_readiness'=>'decision_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']); }
    protected function actionRisk(array $candidate, ?array $entry): array { return (new ActionRiskEvaluationService())->evaluate(['decision_at'=>$this->decisionAt(),'action_candidate'=>$candidate,'selected_parameters'=>$this->parameters($candidate),'entry_reference'=>$entry]); }
    protected function referencePlan(array $candidate): array { $risk=['action_specific_risk'=>$this->actionRisk($candidate,$this->entryReference($candidate))]; return (new TradePlanService())->build(['decision_at'=>$this->decisionAt(),'risk'=>$risk,'action_candidate'=>$candidate,'selected_parameters'=>$this->parameters($candidate),'entry_reference'=>$this->entryReference($candidate)])['reference_plan']; }
    protected function parameters(array $candidate): array { return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->source('tp_optimizer',101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->source('sl_optimizer',102)],'synthetic_test_only'=>true]; }
    protected function source(string $type, int $id): array { return ['registry_artifact_id'=>$id,'artifact_type'=>$type,'schema_version'=>$type.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']]; }
    protected function artifact(bool $decision): array { return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']]; }
    protected function entryReference(array $candidate): array { return ['schema_version'=>'trading_entry_reference_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'fixture-entry-100'],'executable'=>false,'synthetic_test_only'=>true]; }
    protected function capitalContext(): array { return ['schema_version'=>'trading_capital_context_v1','status'=>'reference_only','capital_scope'=>'single_candidate_reference','capital_base'=>['amount'=>1000000.0,'currency'=>'IDR'],'as_of'=>$this->decisionAt(),'source'=>['type'=>'synthetic_test_fixture','identifier'=>'capital-fixture-1m'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function capitalPolicy(array $candidate): array { return ['schema_version'=>'trading_capital_risk_policy_v1','status'=>'reference_only','method'=>'fixed_fractional','maximum_loss_pct'=>1.0,'maximum_loss_amount'=>null,'currency'=>'IDR','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'policy_version'=>'fixed_fractional_reference_v1','source'=>['type'=>'synthetic_test_fixture','identifier'=>'risk-policy-1pct'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function decisionAt(): string { return '2026-07-01T10:00:00+07:00'; }
}
