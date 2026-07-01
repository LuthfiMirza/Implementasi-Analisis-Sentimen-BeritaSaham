<?php

namespace App\Services\Trading;

class PositionSizingService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_position_sizing');
    }

    public function size(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $capitalRisk = $context['capital_risk'] ?? null;
        $actionRisk = $context['action_risk'] ?? null;
        $referencePlan = $context['reference_plan'] ?? null;
        $codes = [];
        $gates = [];
        $candidateAvailable = is_array($candidate);
        $candidateReady = ($candidate['status'] ?? null) === 'candidate_ready';
        $candidateId = $candidate['candidate_id'] ?? null;
        $capitalAvailable = is_array($capitalRisk);
        $capitalEvaluated = ($capitalRisk['status'] ?? null) === 'evaluated_reference';
        $identity = ! $capitalAvailable || ! $candidateAvailable || ($capitalRisk['candidate_id'] ?? null) === $candidateId;
        $grossLoss = $actionRisk['metrics']['gross_loss_per_unit'] ?? $capitalRisk['metrics']['gross_loss_per_unit'] ?? null;
        $maxLoss = $capitalRisk['metrics']['maximum_loss_amount'] ?? null;
        $grossLossOk = is_numeric($grossLoss) && (float) $grossLoss > 0;
        $maxLossOk = is_numeric($maxLoss) && (float) $maxLoss > 0;
        $entry = $referencePlan['entry']['reference_price'] ?? null;
        $entryAvailable = is_numeric($entry) && (float) $entry > 0;
        foreach ([
            ['candidate_available', true, $candidateAvailable, 'CANDIDATE_AVAILABLE', 'POSITION_SIZING_UNAVAILABLE'],
            ['candidate_ready', $candidateAvailable, $candidateAvailable ? $candidateReady : null, 'CANDIDATE_READY', 'POSITION_SIZING_UNAVAILABLE'],
            ['capital_risk_available', true, $capitalAvailable, 'CAPITAL_RISK_AVAILABLE', 'POSITION_SIZING_CAPITAL_RISK_REQUIRED'],
            ['capital_risk_evaluated', $capitalAvailable, $capitalAvailable ? $capitalEvaluated : null, 'CAPITAL_RISK_EVALUATED', 'POSITION_SIZING_CAPITAL_RISK_REQUIRED'],
            ['candidate_identity_match', $capitalAvailable && $candidateAvailable, $capitalAvailable && $candidateAvailable ? $identity : null, 'POSITION_SIZING_IDENTITY_MATCH', 'POSITION_SIZING_IDENTITY_MISMATCH'],
            ['gross_loss_per_unit_available', true, $grossLossOk, 'GROSS_LOSS_AVAILABLE', 'POSITION_SIZING_GROSS_LOSS_REQUIRED'],
            ['maximum_loss_amount_available', $capitalAvailable, $capitalAvailable ? $maxLossOk : null, 'MAXIMUM_LOSS_AVAILABLE', 'POSITION_SIZING_CAPITAL_RISK_REQUIRED'],
            ['numeric_input_validity', $capitalAvailable, $capitalAvailable ? ($grossLossOk && $maxLossOk) : null, 'NUMERIC_INPUT_VALID', 'POSITION_SIZING_GROSS_LOSS_REQUIRED'],
        ] as [$name,$evaluated,$passed,$passCode,$failCode]) { $gates[]=$this->gate($name,$evaluated,$passed,$passed===true?'passed':'blocking',$passed===true?$passCode:$failCode); if($passed===false)$this->add($codes,$failCode); }

        $ready = $candidateReady && $capitalEvaluated && $identity && $grossLossOk && $maxLossOk;
        $raw = $ready ? ((float) $maxLoss / (float) $grossLoss) : null;
        $floor = $raw !== null ? floor($raw) : null;
        $grossAtUnits = $floor !== null ? $floor * (float) $grossLoss : null;
        $reconciled = $grossAtUnits === null || $grossAtUnits <= ((float) $maxLoss + (float) $this->config['reconciliation_tolerance']);
        $referenceNotional = $ready && $entryAvailable ? $floor * (float) $entry : null;
        foreach ([
            ['raw_unit_calculation',$ready,$ready,'POSITION_SIZING_REFERENCE_AVAILABLE'],
            ['floor_reconciliation',$ready,$ready ? $reconciled : null,$reconciled?'FLOOR_RECONCILED':'POSITION_SIZING_GROSS_LOSS_REQUIRED'],
            ['entry_reference_availability',true,$entryAvailable,$entryAvailable?'ENTRY_REFERENCE_AVAILABLE':'TRADE_PLAN_ENTRY_REFERENCE_REQUIRED'],
            ['reference_notional_calculation',$entryAvailable,$entryAvailable ? true : null,'REFERENCE_NOTIONAL_AVAILABLE'],
            ['lot_policy',true,false,'POSITION_SIZING_LOT_POLICY_NOT_IMPLEMENTED'],
            ['cash_validation',true,false,'POSITION_SIZING_CASH_VALIDATION_NOT_IMPLEMENTED'],
            ['liquidity_validation',true,false,'POSITION_SIZING_LIQUIDITY_NOT_IMPLEMENTED'],
            ['execution_cost_validation',true,false,'POSITION_SIZING_EXECUTION_COST_NOT_IMPLEMENTED'],
            ['portfolio_risk_validation',true,false,'POSITION_SIZING_PORTFOLIO_RISK_NOT_IMPLEMENTED'],
            ['execution_capability',true,false,'EXECUTABLE_QUANTITY_UNAVAILABLE'],
        ] as $gate) { [$name,$evaluated,$passed,$code]=$gate; $gates[]=$this->gate($name,$evaluated,$passed,$passed===true?'passed':'blocking',$code); }
        foreach (['POSITION_SIZING_GROSS_ONLY','POSITION_SIZING_LOT_POLICY_NOT_IMPLEMENTED','POSITION_SIZING_CASH_VALIDATION_NOT_IMPLEMENTED','POSITION_SIZING_LIQUIDITY_NOT_IMPLEMENTED','POSITION_SIZING_EXECUTION_COST_NOT_IMPLEMENTED','POSITION_SIZING_PORTFOLIO_RISK_NOT_IMPLEMENTED','POSITION_SIZING_NON_EXECUTABLE','EXECUTABLE_QUANTITY_UNAVAILABLE'] as $code) $this->add($codes,$code);
        if ($ready) $this->add($codes,'POSITION_SIZING_REFERENCE_AVAILABLE');
        $status = $ready ? 'reference_sized' : 'unavailable';
        $result = [
            'schema_version' => $this->config['position_sizing_schema_version'],
            'status' => $status,
            'candidate_id' => $candidateId,
            'candidate_intent' => $candidate['intent'] ?? null,
            'sizing_scope' => 'gross_reference_only',
            'method' => 'fixed_fractional_gross_loss_v1',
            'eligibility' => $ready ? 'reference_sized' : $this->eligibility($candidate, $capitalRisk, $grossLossOk),
            'inputs' => ['maximum_loss_amount'=>$ready?(float)$maxLoss:null,'gross_loss_per_unit'=>$ready?(float)$grossLoss:null,'currency'=>$capitalRisk['metadata']['currency'] ?? null],
            'metrics' => ['raw_reference_units'=>$ready?round($raw,$this->precision()):null,'whole_unit_reference_floor'=>$ready?$floor:null,'reference_notional'=>$referenceNotional,'gross_loss_at_reference_units'=>$ready?round($grossAtUnits,$this->precision()):null,'net_loss_at_reference_units'=>null,'executable_quantity'=>null],
            'constraints' => ['lot_size'=>['status'=>'not_implemented','value'=>null],'liquidity'=>['status'=>'not_implemented'],'cash_availability'=>['status'=>'not_implemented'],'portfolio_exposure'=>['status'=>'not_implemented'],'execution_cost'=>['status'=>'not_implemented']],
            'execution' => ['status'=>'not_executable','approved'=>false],
            'reason_codes' => $this->ordered($codes),
            'metadata' => ['non_executable'=>true,'synthetic_test_only'=>(bool)($capitalRisk['capital_snapshot']['synthetic_test_only']??false)],
            'sizing_gates' => $this->sortGates($gates),
        ];
        $this->validatePositionSizing($result);
        return $result;
    }

    public function validatePositionSizing(array $sizing): void
    {
        if (($sizing['schema_version'] ?? null) !== $this->config['position_sizing_schema_version']) throw new \InvalidArgumentException('invalid sizing schema');
        if (! in_array($sizing['status'] ?? null, ['unavailable','blocked','input_ready','reference_sized','invalid'], true)) throw new \InvalidArgumentException('invalid sizing status');
        if (($sizing['metrics']['executable_quantity'] ?? null) !== null || ($sizing['execution']['approved'] ?? null) !== false) throw new \InvalidArgumentException('sizing must be non executable');
        if (($sizing['metrics']['net_loss_at_reference_units'] ?? null) !== null) throw new \InvalidArgumentException('net sizing unavailable');
        if (($sizing['status'] ?? null) === 'reference_sized' && (($sizing['inputs']['gross_loss_per_unit'] ?? 0) <= 0 || ($sizing['inputs']['maximum_loss_amount'] ?? 0) <= 0)) throw new \InvalidArgumentException('invalid sizing inputs');
        if (count($sizing['reason_codes']) !== count(array_unique($sizing['reason_codes']))) throw new \InvalidArgumentException('duplicate sizing reason');
    }

    protected function eligibility(?array $candidate, ?array $capitalRisk, bool $grossLossOk): string { if(!is_array($candidate))return 'candidate_not_available'; if(($candidate['status']??null)!=='candidate_ready')return 'candidate_not_ready'; if(!is_array($capitalRisk))return 'capital_risk_unavailable'; if(($capitalRisk['status']??null)!=='evaluated_reference')return 'capital_risk_unavailable'; if(!$grossLossOk)return 'gross_loss_per_unit_unavailable'; return 'invalid'; }
    protected function precision(): int { return (int)($this->config['calculation_precision']??6); }
    protected function add(array &$codes,string $code): void { if(!in_array($code,$codes,true))$codes[]=$code; }
    protected function ordered(array $codes): array { sort($codes); return array_values(array_unique($codes)); }
    protected function gate(string $gate,bool $evaluated,?bool $passed,string $severity,string $code,array $details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function sortGates(array $gates): array { $order=array_flip($this->config['sizing_gate_order']); usort($gates,fn($a,$b)=>($order[$a['gate']]??999)<=>($order[$b['gate']]??999)); return $gates; }
}
