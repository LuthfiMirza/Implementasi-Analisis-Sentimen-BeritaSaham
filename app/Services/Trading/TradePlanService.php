<?php

namespace App\Services\Trading;

class TradePlanService
{
    public function __construct(protected ?array $config = null, protected ?TradePlanMaterializationService $materializer = null)
    {
        $this->config ??= config('trading_trade_plan');
        $this->materializer ??= new TradePlanMaterializationService($this->config);
    }

    public function build(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $risk = $context['risk'] ?? [];
        $referencePlan = $this->materializer->materialize([
            'decision_at' => $context['decision_at'] ?? null,
            'action_candidate' => $candidate,
            'selected_parameters' => $context['selected_parameters'] ?? null,
            'action_risk' => $risk['action_specific_risk'] ?? null,
            'entry_reference' => $context['entry_reference'] ?? null,
        ]);
        $status = in_array($referencePlan['status'], ['materialized','parameter_ready'], true) ? $referencePlan['status'] : 'unavailable';
        $executionStatus = $referencePlan['status'] === 'materialized' ? 'reference_ready' : ($referencePlan['status'] === 'parameter_ready' ? 'unavailable' : 'not_implemented');
        $reasonCodes = $this->ordered(array_values(array_unique(array_merge($referencePlan['reason_codes'], ['TRADE_PLAN_EXECUTION_NOT_IMPLEMENTED','TRADE_PLAN_POSITION_SIZING_NOT_IMPLEMENTED','TRADE_PLAN_POSITION_MANAGEMENT_NOT_IMPLEMENTED']))));
        $result = [
            'schema_version' => $this->config['trade_plan_schema_version'],
            'status' => $status,
            'plan_scope' => 'reference_only',
            'candidate_id' => $referencePlan['candidate_id'],
            'candidate_intent' => $referencePlan['candidate_intent'],
            'action' => null,
            'eligibility' => $referencePlan['eligibility'],
            'reference_plan' => $referencePlan,
            'entry' => ['status'=>$referencePlan['entry']['status'],'type'=>null,'price'=>null,'zone_low'=>null,'zone_high'=>null],
            'take_profit' => ['status'=>$referencePlan['take_profit']['status'],'price'=>null,'percentage'=>$referencePlan['take_profit']['percentage'],'source_artifact'=>$referencePlan['take_profit']['source_artifact']],
            'stop_loss' => ['status'=>$referencePlan['stop_loss']['status'],'price'=>null,'percentage'=>$referencePlan['stop_loss']['percentage'],'atr_multiple'=>null,'source_artifact'=>$referencePlan['stop_loss']['source_artifact']],
            'holding' => $referencePlan['holding'],
            'reentry' => $referencePlan['reentry'],
            'invalidation' => $referencePlan['invalidation'],
            'execution_readiness' => ['status'=>$executionStatus,'executable'=>false,'reason_codes'=>['TRADE_PLAN_EXECUTION_NOT_IMPLEMENTED']],
            'position_management' => ['status'=>'not_implemented','reason_codes'=>['POSITION_MANAGEMENT_NOT_IMPLEMENTED','TRADE_PLAN_POSITION_MANAGEMENT_NOT_IMPLEMENTED']],
            'position_sizing' => ['status'=>'not_implemented','quantity'=>null,'capital_fraction'=>null,'reason_codes'=>['TRADE_PLAN_POSITION_SIZING_NOT_IMPLEMENTED']],
            'reason_codes' => $reasonCodes,
            'calculation' => ['method'=>'trade_plan_contract_v1_1','calculated_at'=>$context['decision_at'] ?? null],
        ];
        $this->validateTradePlan($result);
        return $result;
    }

    public function validateTradePlan(array $plan): void
    {
        if (($plan['schema_version'] ?? null) !== $this->config['trade_plan_schema_version']) throw new \InvalidArgumentException('invalid trade plan schema');
        if (! in_array($plan['status'] ?? null, ['unavailable','blocked','research_only','candidate_ready','available','invalid','parameter_ready','materialized'], true)) throw new \InvalidArgumentException('invalid trade plan status');
        $this->materializer->validateReferencePlan($plan['reference_plan']);
        if (($plan['execution_readiness']['executable'] ?? null) !== false || ($plan['execution_readiness']['status'] ?? null) === 'executable') throw new \InvalidArgumentException('trade plan cannot be executable');
        foreach ([['entry','price'],['entry','zone_low'],['entry','zone_high'],['take_profit','price'],['stop_loss','price'],['stop_loss','atr_multiple']] as [$section, $field]) {
            if (($plan[$section][$field] ?? null) !== null) throw new \InvalidArgumentException('executable trade plan field must be null');
        }
        if (($plan['position_sizing']['quantity'] ?? null) !== null || ($plan['position_sizing']['capital_fraction'] ?? null) !== null) throw new \InvalidArgumentException('position sizing must be null');
        if (($plan['action'] ?? null) !== null) throw new \InvalidArgumentException('trade plan action disabled');
    }

    protected function ordered(array $codes): array { sort($codes); return $codes; }
}
