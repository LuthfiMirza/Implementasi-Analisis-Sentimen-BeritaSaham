<?php

namespace App\Services\Trading;

class ExecutionReadinessService
{
    public function __construct(protected ?array $config = null, protected ?ExecutionConstraintEvaluationService $constraints = null)
    {
        $this->config ??= config('trading_execution');
        $this->constraints ??= new ExecutionConstraintEvaluationService($this->config);
    }

    public function assess(array $context): array
    {
        $constraint = $context['constraint_evaluation'] ?? $this->constraints->evaluate($context);
        $codes = $constraint['reason_codes'] ?? [];
        $warnings = $constraint['warnings'] ?? [];
        $blockers = $constraint['blockers'] ?? [];
        $marketStatus = $context['market_constraints']['status'] ?? 'unavailable';
        $cashStatus = $context['execution_cash_context']['status'] ?? 'unavailable';
        $costStatus = $context['execution_cost_evidence']['status'] ?? 'unavailable';
        $liqStatus = $context['liquidity_evidence']['status'] ?? 'unavailable';
        $evaluated = ($constraint['status'] ?? null) === 'constraint_evaluated';
        $partial = $evaluated && ($costStatus === 'unavailable' || $liqStatus === 'unavailable');
        $status = $evaluated ? ($partial ? 'partial' : 'reference_ready') : 'unavailable';
        $eligibility = $evaluated ? ($status === 'reference_ready' ? 'reference_ready' : 'partial_execution_evidence') : ($constraint['eligibility'] ?? 'constraint_blocked');
        if($status==='reference_ready')$this->add($codes,'EXECUTION_REFERENCE_READY');
        if($status==='partial')$this->add($codes,'EXECUTION_READINESS_UNAVAILABLE');
        foreach(['EXECUTION_REFERENCE_ONLY','EXECUTION_PORTFOLIO_RISK_NOT_IMPLEMENTED','EXECUTION_BROKER_CAPABILITY_NOT_IMPLEMENTED','EXECUTABLE_QUANTITY_UNAVAILABLE','EXECUTION_NON_EXECUTABLE_REFERENCE'] as $c)$this->add($codes,$c);
        $gates=[];
        foreach([
            ['constraint_evaluation_available',true,is_array($constraint),'CONSTRAINT_EVALUATION_AVAILABLE'],
            ['constraint_evaluation_valid',is_array($constraint),$evaluated,'CONSTRAINT_EVALUATION_VALID'],
            ['minimum_order_satisfied',$evaluated,$constraint['checks']['minimum_order_satisfied']??null,'MINIMUM_ORDER_SATISFIED'],
            ['cash_sufficiency_known',$evaluated,($constraint['checks']['cash_sufficient']??null)!==null,'CASH_SUFFICIENCY_KNOWN'],
            ['cash_sufficient',$evaluated,$constraint['checks']['cash_sufficient']??null,'EXECUTION_CASH_SUFFICIENT_REFERENCE'],
            ['liquidity_status',true,$liqStatus!=='unavailable','LIQUIDITY_EVIDENCE_AVAILABLE'],
            ['execution_cost_status',true,$costStatus!=='unavailable','EXECUTION_COST_EVIDENCE_AVAILABLE'],
            ['gross_risk_reconciliation',$evaluated,$constraint['checks']['gross_risk_budget_reconciled']??null,'EXECUTION_GROSS_RISK_RECONCILED'],
            ['cost_adjusted_risk_status',true,($constraint['checks']['cost_adjusted_risk_reconciled']??null)!==null,'COST_ADJUSTED_RISK_AVAILABLE'],
            ['portfolio_risk_status',true,false,'EXECUTION_PORTFOLIO_RISK_NOT_IMPLEMENTED'],
            ['broker_capability_status',true,false,'EXECUTION_BROKER_CAPABILITY_NOT_IMPLEMENTED'],
            ['execution_policy_status',true,false,'EXECUTABLE_QUANTITY_UNAVAILABLE'],
            ['final_reference_readiness_classification',true,$evaluated,'EXECUTION_REFERENCE_READY'],
        ] as [$n,$e,$p,$c]) $gates[]=$this->gate($n,$e,$p,$p===true?'passed':'blocking',$c);
        $result=['schema_version'=>$this->config['readiness_schema_version'],'status'=>$status,'candidate_id'=>$constraint['candidate_id']??null,'candidate_intent'=>$constraint['candidate_intent']??null,'readiness_scope'=>'reference_only','eligibility'=>$eligibility,'constraint_evaluation'=>$constraint,'evidence_status'=>['market_constraints'=>$marketStatus,'cash_context'=>$cashStatus,'execution_cost'=>$costStatus,'liquidity'=>$liqStatus,'portfolio_risk'=>'not_implemented','broker_capability'=>'not_implemented'],'reference_quantity'=>$constraint['metrics']['constraint_adjusted_reference_units']??null,'executable_quantity'=>null,'approved'=>false,'reason_codes'=>$this->ordered($codes),'warnings'=>$this->ordered($warnings),'blockers'=>$this->ordered($blockers),'metadata'=>['non_executable'=>true],'readiness_gates'=>$this->sortGates($gates)];
        $this->validateExecutionReadiness($result);
        return $result;
    }

    public function validateExecutionReadiness(array $r): void { if(($r['schema_version']??null)!==$this->config['readiness_schema_version'])throw new \InvalidArgumentException('invalid readiness schema'); if(!in_array($r['status']??null,['unavailable','blocked','partial','reference_ready','invalid'],true))throw new \InvalidArgumentException('invalid readiness status'); if(($r['executable_quantity']??null)!==null||($r['approved']??null)!==false)throw new \InvalidArgumentException('readiness non executable'); if(count($r['reason_codes'])!==count(array_unique($r['reason_codes'])))throw new \InvalidArgumentException('duplicate readiness reason'); }
    protected function gate($gate,$evaluated,$passed,$severity,$code,$details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes,string $code): void { if(!in_array($code,$codes,true))$codes[]=$code; }
    protected function ordered(array $c): array { sort($c); return array_values(array_unique($c)); }
    protected function sortGates(array $g): array { $o=array_flip($this->config['readiness_gate_order']); usort($g,fn($a,$b)=>($o[$a['gate']]??999)<=>($o[$b['gate']]??999)); return $g; }
}
