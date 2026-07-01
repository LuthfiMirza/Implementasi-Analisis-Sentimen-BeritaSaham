<?php

namespace App\Services\Trading;

use Carbon\Carbon;

class ExecutionConstraintEvaluationService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_execution');
    }

    public function evaluate(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $plan = $context['reference_plan'] ?? null;
        $capitalRisk = $context['capital_risk'] ?? null;
        $sizing = $context['position_sizing'] ?? null;
        $market = $context['market_constraints'] ?? null;
        $cash = $context['execution_cash_context'] ?? null;
        $cost = $context['execution_cost_evidence'] ?? null;
        $liquidity = $context['liquidity_evidence'] ?? null;
        $decisionAt = $context['decision_at'] ?? null;
        $codes=[];$warnings=[];$blockers=[];$gates=[];
        $candidateId = $candidate['candidate_id'] ?? null;
        $candidateReady = is_array($candidate) && ($candidate['status'] ?? null) === 'candidate_ready';
        $supportedIntent = is_array($candidate) && in_array($candidate['intent'] ?? null, $this->config['supported_intents'], true);
        $planMaterialized = is_array($plan) && ($plan['status'] ?? null) === 'materialized';
        $capitalEvaluated = is_array($capitalRisk) && ($capitalRisk['status'] ?? null) === 'evaluated_reference';
        $sizingReady = is_array($sizing) && ($sizing['status'] ?? null) === 'reference_sized';
        $identity = $this->identity($candidateId, [$plan, $capitalRisk, $sizing, $market, $cash, $cost, $liquidity]);
        $marketValid = $this->validMarket($market, $decisionAt);
        $cashValid = $this->validCash($cash, $decisionAt);
        $costValid = $cost === null ? null : $this->validCost($cost, $cash['currency'] ?? null, $decisionAt);
        $liquidityValid = $liquidity === null ? null : $this->validLiquidity($liquidity, $decisionAt);
        $currencyMatch = is_array($market) && is_array($cash) && (($market['currency'] ?? null) === ($cash['currency'] ?? null));
        foreach ([
            ['candidate_available',true,is_array($candidate),'CANDIDATE_AVAILABLE','EXECUTION_READINESS_UNAVAILABLE'],
            ['candidate_ready',is_array($candidate),is_array($candidate)?$candidateReady:null,'CANDIDATE_READY','EXECUTION_READINESS_UNAVAILABLE'],
            ['supported_intent',is_array($candidate),is_array($candidate)?$supportedIntent:null,'EXECUTION_INTENT_SUPPORTED','EXECUTION_READINESS_UNAVAILABLE'],
            ['reference_plan_available',true,is_array($plan),'REFERENCE_PLAN_AVAILABLE','EXECUTION_READINESS_UNAVAILABLE'],
            ['reference_plan_materialized',is_array($plan),is_array($plan)?$planMaterialized:null,'REFERENCE_PLAN_MATERIALIZED','EXECUTION_READINESS_UNAVAILABLE'],
            ['capital_risk_evaluated',true,$capitalEvaluated,'CAPITAL_RISK_EVALUATED','EXECUTION_READINESS_UNAVAILABLE'],
            ['position_sizing_reference_sized',true,$sizingReady,'POSITION_SIZING_REFERENCE_AVAILABLE','EXECUTION_READINESS_UNAVAILABLE'],
            ['candidate_identity_consistency',true,$identity,'EXECUTION_IDENTITY_MATCH','EXECUTION_IDENTITY_MISMATCH'],
            ['market_constraints_available',true,is_array($market),'MARKET_CONSTRAINTS_AVAILABLE','EXECUTION_MARKET_CONSTRAINTS_REQUIRED'],
            ['market_constraints_valid',is_array($market),is_array($market)?$marketValid:null,'MARKET_CONSTRAINTS_VALID','EXECUTION_UNIT_STEP_REQUIRED'],
            ['market_constraints_fresh',is_array($market),is_array($market)?$this->fresh($market['as_of']??null,$decisionAt):null,'MARKET_CONSTRAINTS_FRESH','EXECUTION_EVIDENCE_STALE'],
            ['cash_context_available',true,is_array($cash),'CASH_CONTEXT_AVAILABLE','EXECUTION_CASH_CONTEXT_REQUIRED'],
            ['cash_context_valid',is_array($cash),is_array($cash)?$cashValid:null,'CASH_CONTEXT_VALID','EXECUTION_CASH_CONTEXT_REQUIRED'],
            ['cash_context_fresh',is_array($cash),is_array($cash)?$this->fresh($cash['as_of']??null,$decisionAt):null,'CASH_CONTEXT_FRESH','EXECUTION_EVIDENCE_STALE'],
            ['currency_match',is_array($market)&&is_array($cash),is_array($market)&&is_array($cash)?$currencyMatch:null,'CURRENCY_MATCH','EXECUTION_IDENTITY_MISMATCH'],
        ] as [$n,$e,$p,$pc,$fc]) { $gates[]=$this->gate($n,$e,$p,$p===true?'passed':'blocking',$p===true?$pc:$fc); if($p===false)$this->add($codes,$fc,$blockers); }
        $raw = $sizing['metrics']['whole_unit_reference_floor'] ?? null;
        $entry = $plan['entry']['reference_price'] ?? null;
        $grossLossUnit = $capitalRisk['metrics']['gross_loss_per_unit'] ?? null;
        $maxLoss = $capitalRisk['metrics']['maximum_loss_amount'] ?? null;
        $unitStep = $market['unit_step'] ?? null;
        $minUnits = $market['minimum_order_units'] ?? null;
        $stepAligned = ($sizingReady && $marketValid) ? floor(((float)$raw) / (int)$unitStep) * (int)$unitStep : null;
        $minOk = $stepAligned !== null && ($minUnits === null || $stepAligned >= (float)$minUnits);
        $cashCap = ($cashValid && is_numeric($entry) && (float)$entry > 0 && $marketValid) ? floor(floor(((float)$cash['available_cash']) / (float)$entry) / (int)$unitStep) * (int)$unitStep : null;
        $liqCap = ($liquidityValid && isset($liquidity['maximum_reference_units']) && is_numeric($liquidity['maximum_reference_units']) && $marketValid) ? floor(((float)$liquidity['maximum_reference_units']) / (int)$unitStep) * (int)$unitStep : null;
        $caps = array_filter([$stepAligned, $cashCap, $liqCap], fn($v)=>$v!==null);
        $adjusted = count($caps) ? min($caps) : null;
        $notional = $adjusted !== null && is_numeric($entry) ? $adjusted * (float)$entry : null;
        $grossLoss = $adjusted !== null && is_numeric($grossLossUnit) ? $adjusted * (float)$grossLossUnit : null;
        $grossOk = $grossLoss !== null && is_numeric($maxLoss) && $grossLoss <= (float)$maxLoss + (float)$this->config['reconciliation_tolerance'];
        $cashSufficient = $cashCap !== null && $stepAligned !== null ? $cashCap >= $stepAligned : null;
        $costAmount = $this->costAmount($costValid ? $cost : null, $notional);
        $costAdjusted = $costAmount !== null && $grossLoss !== null ? $grossLoss + $costAmount : null;
        foreach ([
            ['unit_step_alignment',$marketValid,$marketValid&&$stepAligned!==null,'EXECUTION_REFERENCE_QUANTITY_ALIGNED','EXECUTION_UNIT_STEP_REQUIRED'],
            ['minimum_order_validation',$stepAligned!==null,$stepAligned!==null?$minOk:null,'MINIMUM_ORDER_SATISFIED','EXECUTION_MINIMUM_ORDER_NOT_SATISFIED'],
            ['cash_cap_calculation',$cashValid,$cashValid&&$cashCap!==null,'EXECUTION_REFERENCE_QUANTITY_CASH_CAPPED','EXECUTION_CASH_CONTEXT_REQUIRED'],
            ['optional_liquidity_cap_calculation',$liquidity!==null,$liquidity!==null?$liquidityValid:null,'EXECUTION_REFERENCE_QUANTITY_LIQUIDITY_CAPPED','EXECUTION_LIQUIDITY_EVIDENCE_UNAVAILABLE'],
            ['gross_risk_reconciliation',$adjusted!==null,$adjusted!==null?$grossOk:null,'EXECUTION_GROSS_RISK_RECONCILED','EXECUTION_CASH_INSUFFICIENT'],
            ['optional_cost_risk_reconciliation',$cost!==null,$cost!==null?($costAdjusted!==null):null,'EXECUTION_COST_REFERENCE_AVAILABLE','EXECUTION_COST_EVIDENCE_UNAVAILABLE'],
            ['non_executable_capability',true,true,'EXECUTION_NON_EXECUTABLE_REFERENCE','EXECUTION_NON_EXECUTABLE_REFERENCE'],
        ] as [$n,$e,$p,$pc,$fc]) { $gates[]=$this->gate($n,$e,$p,$p===true?'passed':'blocking',$p===true?$pc:$fc); if($p===false && $n!=='optional_liquidity_cap_calculation' && $n!=='optional_cost_risk_reconciliation')$this->add($codes,$fc,$blockers); }
        if($stepAligned!==null)$this->add($codes,'EXECUTION_REFERENCE_QUANTITY_ALIGNED');
        if($cashCap!==null)$this->add($codes,'EXECUTION_REFERENCE_QUANTITY_CASH_CAPPED');
        if($liqCap!==null)$this->add($codes,'EXECUTION_REFERENCE_QUANTITY_LIQUIDITY_CAPPED'); else $this->add($codes,'EXECUTION_LIQUIDITY_UNKNOWN',$warnings);
        if($cashSufficient===true)$this->add($codes,'EXECUTION_CASH_SUFFICIENT_REFERENCE'); elseif($cashSufficient===false)$this->add($codes,'EXECUTION_CASH_INSUFFICIENT',$blockers);
        if($grossOk)$this->add($codes,'EXECUTION_GROSS_RISK_RECONCILED');
        if($costAmount===null)$this->add($codes,'EXECUTION_COST_ADJUSTED_RISK_UNAVAILABLE',$warnings);
        foreach(['EXECUTION_REFERENCE_ONLY','EXECUTION_PORTFOLIO_RISK_NOT_IMPLEMENTED','EXECUTION_BROKER_CAPABILITY_NOT_IMPLEMENTED','EXECUTABLE_QUANTITY_UNAVAILABLE','EXECUTION_NON_EXECUTABLE_REFERENCE'] as $c)$this->add($codes,$c,$blockers);
        $allCore = $candidateReady&&$supportedIntent&&$planMaterialized&&$capitalEvaluated&&$sizingReady&&$identity&&$marketValid&&$cashValid&&$currencyMatch&&$stepAligned!==null&&$minOk&&$cashSufficient!==false&&$grossOk;
        $status = $allCore ? 'constraint_evaluated' : (is_array($candidate)||is_array($plan)||is_array($sizing)?'unavailable':'unavailable');
        $result=['schema_version'=>$this->config['constraint_schema_version'],'status'=>$status,'candidate_id'=>$candidateId,'candidate_intent'=>$candidate['intent']??null,'evaluation_scope'=>'reference_non_executable','eligibility'=>$allCore?'eligible_for_reference_readiness':$this->eligibility($candidate,$plan,$capitalRisk,$sizing,$market,$cash),'inputs'=>['raw_reference_units'=>$sizing['metrics']['raw_reference_units']??null,'whole_unit_reference_floor'=>$raw,'entry_reference_price'=>$entry,'available_cash'=>$cash['available_cash']??null,'unit_step'=>$unitStep,'minimum_order_units'=>$minUnits],'metrics'=>['step_aligned_reference_units'=>$stepAligned,'cash_capped_reference_units'=>$cashCap,'liquidity_capped_reference_units'=>$liqCap,'constraint_adjusted_reference_units'=>$adjusted,'reference_notional'=>$notional,'gross_loss_at_adjusted_units'=>$grossLoss,'estimated_execution_cost'=>$costAmount,'cost_adjusted_reference_loss'=>$costAdjusted,'executable_quantity'=>null],'checks'=>['minimum_order_satisfied'=>$stepAligned===null?null:$minOk,'cash_sufficient'=>$cashSufficient,'liquidity_sufficient'=>$liqCap===null?null:($liqCap >= $adjusted),'gross_risk_budget_reconciled'=>$adjusted===null?null:$grossOk,'cost_adjusted_risk_reconciled'=>$costAdjusted===null?null:($costAdjusted <= (float)$maxLoss + (float)$this->config['reconciliation_tolerance'])],'reason_codes'=>$this->ordered($codes),'warnings'=>$this->ordered($warnings),'blockers'=>$this->ordered($blockers),'metadata'=>['non_executable'=>true,'applied_caps'=>array_values(array_filter(['step'=>$stepAligned!==null?'step':null,'cash'=>$cashCap!==null?'cash':null,'liquidity'=>$liqCap!==null?'liquidity':null]))],'constraint_gates'=>$this->sortGates($gates)];
        $this->validateConstraintEvaluation($result);
        return $result;
    }

    public function validateConstraintEvaluation(array $r): void { if(($r['schema_version']??null)!==$this->config['constraint_schema_version'])throw new \InvalidArgumentException('invalid constraint schema'); if(!in_array($r['status']??null,['unavailable','blocked','input_ready','constraint_evaluated','invalid'],true))throw new \InvalidArgumentException('invalid constraint status'); if(($r['metrics']['executable_quantity']??null)!==null)throw new \InvalidArgumentException('executable quantity disabled'); $adj=$r['metrics']['constraint_adjusted_reference_units']??null; $raw=$r['inputs']['whole_unit_reference_floor']??null; if($adj!==null&&$raw!==null&&$adj>$raw)throw new \InvalidArgumentException('adjusted exceeds raw'); if(count($r['reason_codes'])!==count(array_unique($r['reason_codes'])))throw new \InvalidArgumentException('duplicate execution reason'); }
    protected function validMarket(?array $m,?string $d): bool { return is_array($m)&&($m['schema_version']??null)===$this->config['market_constraints_schema_version']&&($m['status']??null)==='reference_only'&&is_int($m['unit_step']??null)&&$m['unit_step']>0&&(($m['minimum_order_units']??0)>=0)&&!empty($m['source'])&&($m['approved_for_execution']??null)===false&&$this->fresh($m['as_of']??null,$d); }
    protected function validCash(?array $c,?string $d): bool { return is_array($c)&&($c['schema_version']??null)===$this->config['cash_context_schema_version']&&($c['status']??null)==='reference_only'&&is_numeric($c['available_cash']??null)&&$c['available_cash']>=0&&!empty($c['currency'])&&!empty($c['source'])&&($c['approved_for_execution']??null)===false&&$this->fresh($c['as_of']??null,$d); }
    protected function validCost(?array $c,?string $cur,?string $d): bool { foreach(['entry_cost_bps','exit_cost_bps','entry_slippage_bps','exit_slippage_bps','fixed_cost_amount'] as $k) if(($c[$k]??0)<0)return false; return is_array($c)&&($c['schema_version']??null)===$this->config['execution_cost_schema_version']&&($c['status']??null)==='reference_only'&&($c['currency']??null)===$cur&&!empty($c['source'])&&($c['approved_for_execution']??null)===false&&$this->fresh($c['as_of']??null,$d); }
    protected function validLiquidity(?array $l,?string $d): bool { return is_array($l)&&($l['schema_version']??null)===$this->config['liquidity_schema_version']&&($l['status']??null)==='reference_only'&&!empty($l['source'])&&($l['approved_for_execution']??null)===false&&$this->fresh($l['as_of']??null,$d); }
    protected function costAmount(?array $c,$notional): ?float { if(!$c||$notional===null)return null; $bps=($c['entry_cost_bps']??0)+($c['exit_cost_bps']??0)+($c['entry_slippage_bps']??0)+($c['exit_slippage_bps']??0); return round(((float)$notional)*$bps/10000+(float)($c['fixed_cost_amount']??0),$this->config['precision']); }
    protected function identity($id,array $items): bool { foreach($items as $i) if(is_array($i)&&isset($i['candidate_id'])&&$i['candidate_id']!==$id)return false; return true; }
    protected function eligibility($c,$p,$cr,$s,$m,$cash): string { if(!is_array($c))return 'candidate_unavailable'; if(!is_array($p)||($p['status']??null)!=='materialized')return 'reference_plan_unavailable'; if(!is_array($cr)||($cr['status']??null)!=='evaluated_reference')return 'capital_risk_unavailable'; if(!is_array($s)||($s['status']??null)!=='reference_sized')return 'position_sizing_unavailable'; if(!is_array($m))return 'market_constraints_unavailable'; if(!is_array($cash))return 'cash_context_unavailable'; return 'constraint_blocked'; }
    protected function fresh(?string $asOf,?string $d): bool { if(!$asOf||!$d)return false; try{$a=Carbon::parse($asOf);$dec=Carbon::parse($d);}catch(\Throwable){return false;} return $a->lessThanOrEqualTo($dec)&&$a->greaterThanOrEqualTo($dec->copy()->subMinutes($this->config['timestamp_freshness_minutes'])); }
    protected function gate($gate,$evaluated,$passed,$severity,$code,$details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes,string $code,?array &$target=null): void { if(!in_array($code,$codes,true))$codes[]=$code; if(is_array($target)&&!in_array($code,$target,true))$target[]=$code; }
    protected function ordered(array $c): array { sort($c); return array_values(array_unique($c)); }
    protected function sortGates(array $g): array { $o=array_flip($this->config['constraint_gate_order']); usort($g,fn($a,$b)=>($o[$a['gate']]??999)<=>($o[$b['gate']]??999)); return $g; }
}
