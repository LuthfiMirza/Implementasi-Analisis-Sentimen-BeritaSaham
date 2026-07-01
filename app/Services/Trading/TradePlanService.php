<?php

namespace App\Services\Trading;

class TradePlanService
{
    public function __construct(protected ?array $config = null, protected ?TradePlanMaterializationService $materializer = null, protected ?ExecutionReadinessService $executionReadinessService = null)
    {
        $this->config ??= config('trading_trade_plan');
        $this->materializer ??= new TradePlanMaterializationService($this->config);
        $this->executionReadinessService ??= new ExecutionReadinessService();
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
        $sizing = $risk['position_sizing'] ?? ['status' => 'unavailable'];
        $status = in_array($referencePlan['status'], ['materialized','parameter_ready'], true) ? $referencePlan['status'] : 'unavailable';
        $executionStatus = $referencePlan['status'] === 'materialized' ? 'reference_ready' : ($referencePlan['status'] === 'parameter_ready' ? 'unavailable' : 'not_implemented');
        $executionReadiness = $this->executionReadinessService->assess([
            'decision_at' => $context['decision_at'] ?? null,
            'action_candidate' => $candidate,
            'reference_plan' => $referencePlan,
            'capital_risk' => $risk['capital_risk'] ?? null,
            'position_sizing' => $risk['position_sizing'] ?? null,
            'market_constraints' => $context['market_constraints'] ?? null,
            'execution_cash_context' => $context['execution_cash_context'] ?? null,
            'execution_cost_evidence' => $context['execution_cost_evidence'] ?? null,
            'liquidity_evidence' => $context['liquidity_evidence'] ?? null,
        ]);
        $executionStatus = $executionReadiness['status'] === 'reference_ready' ? 'reference_ready' : $executionReadiness['status'];
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
            'execution_readiness' => $executionReadiness + ['executable'=>false],
            'position_management' => $context['position_management'] ?? ['status'=>'not_implemented','management_action_candidate'=>null,'executable_instruction'=>null,'reason_codes'=>['POSITION_MANAGEMENT_NOT_IMPLEMENTED','TRADE_PLAN_POSITION_MANAGEMENT_NOT_IMPLEMENTED']],
            'position_sizing' => [
                'schema_version' => $sizing['schema_version'] ?? null,
                'status' => $sizing['status'] ?? 'unavailable',
                'reference_units' => $sizing['metrics']['whole_unit_reference_floor'] ?? null,
                'raw_reference_units' => $sizing['metrics']['raw_reference_units'] ?? null,
                'reference_notional' => $sizing['metrics']['reference_notional'] ?? null,
                'executable_quantity' => null,
                'execution_approved' => false,
                'quantity'=>null,
                'capital_fraction'=>null,
                'reason_codes'=>$sizing['reason_codes'] ?? ['TRADE_PLAN_POSITION_SIZING_NOT_IMPLEMENTED'],
            ],
            'portfolio_readiness' => [
                'schema_version' => $risk['portfolio_risk']['schema_version'] ?? null,
                'status' => $risk['portfolio_risk']['status'] ?? 'unavailable',
                'approved' => false,
                'reason_codes' => $risk['portfolio_risk']['reason_codes'] ?? ['PORTFOLIO_RISK_UNAVAILABLE'],
            ],
            'portfolio_approval' => [
                'schema_version' => $context['portfolio_approval']['schema_version'] ?? config('trading_portfolio_approval.portfolio_approval_schema_version'),
                'status' => $context['portfolio_approval']['status'] ?? 'unavailable',
                'reference_approved' => $context['portfolio_approval']['approval_result']['reference_approved'] ?? false,
                'production_approved' => false,
                'execution_approved' => false,
                'reason_codes' => $context['portfolio_approval']['reason_codes'] ?? ['PORTFOLIO_APPROVAL_UNAVAILABLE'],
            ],
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
        if (($plan['position_sizing']['quantity'] ?? null) !== null || ($plan['position_sizing']['capital_fraction'] ?? null) !== null || ($plan['position_sizing']['executable_quantity'] ?? null) !== null || ($plan['position_sizing']['execution_approved'] ?? null) !== false) throw new \InvalidArgumentException('position sizing must be non executable');
        if (($plan['action'] ?? null) !== null) throw new \InvalidArgumentException('trade plan action disabled');
    }

    protected function ordered(array $codes): array { sort($codes); return $codes; }
}
