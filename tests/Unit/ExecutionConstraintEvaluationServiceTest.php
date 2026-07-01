<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionRiskEvaluationService;
use App\Services\Trading\CapitalRiskEvaluationService;
use App\Services\Trading\ExecutionConstraintEvaluationService;
use App\Services\Trading\PositionSizingService;
use App\Services\Trading\TradePlanService;
use Tests\TestCase;

class ExecutionConstraintEvaluationServiceTest extends TestCase
{
    public function test_missing_inputs_unavailable(): void
    {
        $r=(new ExecutionConstraintEvaluationService())->evaluate(['decision_at'=>$this->decisionAt()]);
        $this->assertSame('trading_execution_constraints_v1',$r['schema_version']);
        $this->assertSame('unavailable',$r['status']);
        $this->assertContains('EXECUTION_MARKET_CONSTRAINTS_REQUIRED',$r['reason_codes']);
        $this->assertNull($r['metrics']['executable_quantity']);
    }

    public function test_aligned_reference_size_without_cost_or_liquidity(): void
    {
        $r=(new ExecutionConstraintEvaluationService())->evaluate($this->context());
        $this->assertSame('constraint_evaluated',$r['status']);
        $this->assertSame(5000.0,$r['metrics']['step_aligned_reference_units']);
        $this->assertSame(6000.0,$r['metrics']['cash_capped_reference_units']);
        $this->assertNull($r['metrics']['liquidity_capped_reference_units']);
        $this->assertSame(5000.0,$r['metrics']['constraint_adjusted_reference_units']);
        $this->assertSame(500000.0,$r['metrics']['reference_notional']);
        $this->assertSame(10000.0,$r['metrics']['gross_loss_at_adjusted_units']);
        $this->assertTrue($r['checks']['cash_sufficient']);
        $this->assertTrue($r['checks']['gross_risk_budget_reconciled']);
        $this->assertNull($r['metrics']['cost_adjusted_reference_loss']);
        $this->assertNull($r['metrics']['executable_quantity']);
    }

    public function test_cash_cap_and_minimum_order_failure(): void
    {
        $ctx=$this->context(300000.0);
        $cash=(new ExecutionConstraintEvaluationService())->evaluate($ctx);
        $this->assertSame(3000.0,$cash['metrics']['cash_capped_reference_units']);
        $this->assertSame(3000.0,$cash['metrics']['constraint_adjusted_reference_units']);
        $this->assertSame(300000.0,$cash['metrics']['reference_notional']);
        $this->assertSame(6000.0,$cash['metrics']['gross_loss_at_adjusted_units']);

        $ctx=$this->context(5000.0);
        $ctx['market_constraints']['minimum_order_units']=10000;
        $blocked=(new ExecutionConstraintEvaluationService())->evaluate($ctx);
        $this->assertContains('EXECUTION_MINIMUM_ORDER_NOT_SATISFIED',$blocked['reason_codes']);
        $this->assertFalse($blocked['checks']['minimum_order_satisfied']);
    }

    public function test_liquidity_cap_and_cost_evidence(): void
    {
        $ctx=$this->context();
        $ctx['liquidity_evidence']=$this->liquidity($ctx['action_candidate'], 2500);
        $ctx['execution_cost_evidence']=$this->cost($ctx['action_candidate']);
        $r=(new ExecutionConstraintEvaluationService())->evaluate($ctx);
        $this->assertSame(2500.0,$r['metrics']['liquidity_capped_reference_units']);
        $this->assertSame(2500.0,$r['metrics']['constraint_adjusted_reference_units']);
        $this->assertSame(250000.0,$r['metrics']['reference_notional']);
        $this->assertSame(750.0,$r['metrics']['estimated_execution_cost']);
        $this->assertSame(5750.0,$r['metrics']['cost_adjusted_reference_loss']);
    }

    public function test_validator_rejects_executable_quantity(): void
    {
        $svc=new ExecutionConstraintEvaluationService();
        $r=$svc->evaluate($this->context());
        $r['metrics']['executable_quantity']=1;
        $this->expectException(\InvalidArgumentException::class);
        $svc->validateConstraintEvaluation($r);
    }

    protected function context(float $cash=600000.0): array { $c=$this->candidate(); $params=$this->parameters($c); $entry=$this->entry($c); $ar=(new ActionRiskEvaluationService())->evaluate(['decision_at'=>$this->decisionAt(),'action_candidate'=>$c,'selected_parameters'=>$params,'entry_reference'=>$entry]); $plan=(new TradePlanService())->build(['decision_at'=>$this->decisionAt(),'risk'=>['action_specific_risk'=>$ar],'action_candidate'=>$c,'selected_parameters'=>$params,'entry_reference'=>$entry])['reference_plan']; $cr=(new CapitalRiskEvaluationService())->evaluate(['decision_at'=>$this->decisionAt(),'action_candidate'=>$c,'action_risk'=>$ar,'reference_plan'=>$plan,'capital_context'=>$this->capitalContext(),'capital_risk_policy'=>$this->policy($c)]); $sz=(new PositionSizingService())->size(['action_candidate'=>$c,'capital_risk'=>$cr,'action_risk'=>$ar,'reference_plan'=>$plan]); return ['decision_at'=>$this->decisionAt(),'action_candidate'=>$c,'reference_plan'=>$plan,'capital_risk'=>$cr,'position_sizing'=>$sz,'market_constraints'=>$this->market($c),'execution_cash_context'=>$this->cash($c,$cash)]; }
    protected function candidate(): array { return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact(true),'sl_optimizer'=>$this->artifact(true)],'evidence_readiness'=>'decision_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']); }
    protected function parameters($c): array { return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$c['candidate_id'],'candidate_intent'=>$c['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->source('tp_optimizer',101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->source('sl_optimizer',102)],'synthetic_test_only'=>true]; }
    protected function source($t,$id): array { return ['registry_artifact_id'=>$id,'artifact_type'=>$t,'schema_version'=>$t.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']]; }
    protected function artifact($d): array { return ['latest_decision_available'=>$d,'selected_available'=>$d,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']]; }
    protected function entry($c): array { return ['schema_version'=>'trading_entry_reference_v1','ticker'=>'BUMI','candidate_id'=>$c['candidate_id'],'candidate_intent'=>$c['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'entry'],'executable'=>false,'synthetic_test_only'=>true]; }
    protected function capitalContext(): array { return ['schema_version'=>'trading_capital_context_v1','status'=>'reference_only','capital_scope'=>'single_candidate_reference','capital_base'=>['amount'=>1000000.0,'currency'=>'IDR'],'as_of'=>$this->decisionAt(),'source'=>['type'=>'synthetic_test_fixture','identifier'=>'capital'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function policy($c): array { return ['schema_version'=>'trading_capital_risk_policy_v1','status'=>'reference_only','method'=>'fixed_fractional','maximum_loss_pct'=>1.0,'maximum_loss_amount'=>null,'currency'=>'IDR','candidate_id'=>$c['candidate_id'],'candidate_intent'=>$c['intent'],'policy_version'=>'fixed_fractional_reference_v1','source'=>['type'=>'synthetic_test_fixture','identifier'=>'policy'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function market($c): array { return ['schema_version'=>'trading_market_constraints_v1','status'=>'reference_only','ticker'=>'BUMI','candidate_id'=>$c['candidate_id'],'market'=>'synthetic','currency'=>'IDR','unit_step'=>100,'minimum_order_units'=>100,'maximum_order_units'=>null,'price_step'=>null,'minimum_notional'=>null,'as_of'=>$this->decisionAt(),'source'=>['type'=>'synthetic_test_fixture','identifier'=>'market'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function cash($c,$amount): array { return ['schema_version'=>'trading_execution_cash_context_v1','status'=>'reference_only','candidate_id'=>$c['candidate_id'],'currency'=>'IDR','available_cash'=>$amount,'reserved_cash'=>null,'as_of'=>$this->decisionAt(),'source'=>['type'=>'synthetic_test_fixture','identifier'=>'cash'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function liquidity($c,$max): array { return ['schema_version'=>'trading_liquidity_evidence_v1','status'=>'reference_only','ticker'=>'BUMI','candidate_id'=>$c['candidate_id'],'as_of'=>$this->decisionAt(),'reference_volume_units'=>null,'maximum_reference_units'=>$max,'source'=>['type'=>'synthetic_test_fixture','identifier'=>'liq'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function cost($c): array { return ['schema_version'=>'trading_execution_cost_evidence_v1','status'=>'reference_only','candidate_id'=>$c['candidate_id'],'currency'=>'IDR','entry_cost_bps'=>10,'exit_cost_bps'=>10,'entry_slippage_bps'=>5,'exit_slippage_bps'=>5,'fixed_cost_amount'=>0,'as_of'=>$this->decisionAt(),'source'=>['type'=>'synthetic_test_fixture','identifier'=>'cost'],'approved_for_execution'=>false,'synthetic_test_only'=>true]; }
    protected function decisionAt(): string { return '2026-07-01T10:00:00+07:00'; }
}
