<?php

namespace Tests\Unit;

use App\Services\Trading\ExecutionReadinessService;
use Tests\TestCase;

class ExecutionReadinessServiceTest extends TestCase
{
    public function test_constraints_unavailable(): void
    {
        $r=(new ExecutionReadinessService())->assess(['decision_at'=>'2026-07-01T10:00:00+07:00']);
        $this->assertSame('trading_execution_readiness_v1',$r['schema_version']);
        $this->assertSame('unavailable',$r['status']);
        $this->assertNull($r['executable_quantity']);
        $this->assertFalse($r['approved']);
    }

    public function test_partial_without_cost_and_liquidity(): void
    {
        $constraint=['schema_version'=>'trading_execution_constraints_v1','status'=>'constraint_evaluated','candidate_id'=>'abc','candidate_intent'=>'long_entry','eligibility'=>'eligible_for_reference_readiness','metrics'=>['constraint_adjusted_reference_units'=>5000,'executable_quantity'=>null],'checks'=>['minimum_order_satisfied'=>true,'cash_sufficient'=>true,'gross_risk_budget_reconciled'=>true,'cost_adjusted_risk_reconciled'=>null],'reason_codes'=>['EXECUTION_GROSS_RISK_RECONCILED'],'warnings'=>[],'blockers'=>[]];
        $r=(new ExecutionReadinessService())->assess(['constraint_evaluation'=>$constraint]);
        $this->assertSame('partial',$r['status']);
        $this->assertSame('partial_execution_evidence',$r['eligibility']);
        $this->assertSame(5000,$r['reference_quantity']);
        $this->assertNull($r['executable_quantity']);
        $this->assertContains('EXECUTION_BROKER_CAPABILITY_NOT_IMPLEMENTED',$r['reason_codes']);
    }

    public function test_reference_ready_with_explicit_cost_and_liquidity_still_non_executable(): void
    {
        $constraint=['schema_version'=>'trading_execution_constraints_v1','status'=>'constraint_evaluated','candidate_id'=>'abc','candidate_intent'=>'long_entry','eligibility'=>'eligible_for_reference_readiness','metrics'=>['constraint_adjusted_reference_units'=>2500,'executable_quantity'=>null],'checks'=>['minimum_order_satisfied'=>true,'cash_sufficient'=>true,'gross_risk_budget_reconciled'=>true,'cost_adjusted_risk_reconciled'=>true],'reason_codes'=>['EXECUTION_GROSS_RISK_RECONCILED'],'warnings'=>[],'blockers'=>[]];
        $r=(new ExecutionReadinessService())->assess(['constraint_evaluation'=>$constraint,'execution_cost_evidence'=>['status'=>'reference_only'],'liquidity_evidence'=>['status'=>'reference_only']]);
        $this->assertSame('reference_ready',$r['status']);
        $this->assertSame('reference_ready',$r['eligibility']);
        $this->assertSame(2500,$r['reference_quantity']);
        $this->assertNull($r['executable_quantity']);
        $this->assertFalse($r['approved']);
        $this->assertContains('EXECUTION_REFERENCE_READY',$r['reason_codes']);
    }

    public function test_validator_rejects_approval(): void
    {
        $svc=new ExecutionReadinessService();
        $r=$svc->assess(['decision_at'=>'2026-07-01T10:00:00+07:00']);
        $r['approved']=true;
        $this->expectException(\InvalidArgumentException::class);
        $svc->validateExecutionReadiness($r);
    }
}
