<?php

namespace App\Services\Trading;

use Carbon\Carbon;

class CapitalRiskEvaluationService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_position_sizing');
    }

    public function evaluate(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $actionRisk = $context['action_risk'] ?? null;
        $referencePlan = $context['reference_plan'] ?? null;
        $capitalContext = $context['capital_context'] ?? null;
        $policy = $context['capital_risk_policy'] ?? null;
        $decisionAt = $context['decision_at'] ?? null;
        $codes = [];
        $limitations = [];
        $gates = [];

        $candidateAvailable = is_array($candidate);
        $candidateReady = ($candidate['status'] ?? null) === 'candidate_ready';
        $supportedIntent = in_array($candidate['intent'] ?? null, $this->config['supported_intents'], true);
        $candidateId = $candidate['candidate_id'] ?? null;
        $actionRiskAvailable = is_array($actionRisk);
        $actionRiskEvaluated = ($actionRisk['status'] ?? null) === 'evaluated';
        $riskIdentity = $actionRiskAvailable && $candidateAvailable && ($actionRisk['candidate_id'] ?? null) === $candidateId;
        $referencePlanAvailable = is_array($referencePlan) && in_array($referencePlan['status'] ?? null, ['parameter_ready', 'materialized'], true);
        $referenceIdentity = ! is_array($referencePlan) || ! $candidateAvailable || ($referencePlan['candidate_id'] ?? null) === $candidateId;
        $contextAvailable = is_array($capitalContext);
        $contextValid = $this->validCapitalContext($capitalContext, $decisionAt);
        $policyAvailable = is_array($policy);
        $policyValid = $this->validPolicy($policy);
        $policyIdentity = $policyAvailable && $candidateAvailable && ($policy['candidate_id'] ?? null) === $candidateId && ($policy['candidate_intent'] ?? null) === ($candidate['intent'] ?? null);
        $currencyMatch = $contextAvailable && $policyAvailable && (($capitalContext['capital_base']['currency'] ?? null) === ($policy['currency'] ?? null));
        $grossLoss = $actionRisk['metrics']['gross_loss_per_unit'] ?? null;
        $grossLossAvailable = is_numeric($grossLoss) && (float) $grossLoss > 0;

        $checks = [
            ['candidate_available', true, $candidateAvailable, 'CAPITAL_RISK_CANDIDATE_AVAILABLE', 'CAPITAL_CONTEXT_UNAVAILABLE'],
            ['candidate_valid', $candidateAvailable, $candidateAvailable ? (($candidate['schema_version'] ?? null) === config('trading_action.schema_version')) : null, 'CAPITAL_RISK_CANDIDATE_VALID', 'CAPITAL_CONTEXT_INVALID'],
            ['candidate_ready', $candidateAvailable, $candidateAvailable ? $candidateReady : null, 'CAPITAL_RISK_CANDIDATE_READY', 'CAPITAL_CONTEXT_UNAVAILABLE'],
            ['supported_intent', $candidateAvailable, $candidateAvailable ? $supportedIntent : null, 'CAPITAL_RISK_INTENT_SUPPORTED', 'CAPITAL_RISK_POLICY_INVALID'],
            ['action_risk_available', true, $actionRiskAvailable, 'ACTION_RISK_AVAILABLE', 'ACTION_RISK_REQUIRED_FOR_CAPITAL_RISK'],
            ['action_risk_evaluated', $actionRiskAvailable, $actionRiskAvailable ? $actionRiskEvaluated : null, 'ACTION_RISK_EVALUATED', 'ACTION_RISK_REQUIRED_FOR_CAPITAL_RISK'],
            ['candidate_identity_match', $actionRiskAvailable && $candidateAvailable, $actionRiskAvailable && $candidateAvailable ? $riskIdentity : null, 'CAPITAL_RISK_IDENTITY_MATCH', 'CAPITAL_RISK_IDENTITY_MISMATCH'],
            ['reference_plan_available', true, $referencePlanAvailable, 'REFERENCE_PLAN_AVAILABLE', 'CAPITAL_CONTEXT_UNAVAILABLE'],
            ['reference_plan_identity_match', is_array($referencePlan) && $candidateAvailable, is_array($referencePlan) && $candidateAvailable ? $referenceIdentity : null, 'REFERENCE_PLAN_IDENTITY_MATCH', 'CAPITAL_RISK_IDENTITY_MISMATCH'],
            ['capital_context_available', true, $contextAvailable, 'CAPITAL_CONTEXT_AVAILABLE', 'CAPITAL_CONTEXT_UNAVAILABLE'],
            ['capital_context_valid', $contextAvailable, $contextAvailable ? $contextValid : null, 'CAPITAL_CONTEXT_VALID', 'CAPITAL_CONTEXT_INVALID'],
            ['capital_context_fresh', $contextAvailable, $contextAvailable ? $this->fresh($capitalContext['as_of'] ?? null, $decisionAt) : null, 'CAPITAL_CONTEXT_FRESH', 'CAPITAL_CONTEXT_STALE'],
            ['capital_policy_available', true, $policyAvailable, 'CAPITAL_RISK_POLICY_AVAILABLE', 'CAPITAL_RISK_POLICY_UNAVAILABLE'],
            ['capital_policy_valid', $policyAvailable, $policyAvailable ? $policyValid : null, 'CAPITAL_RISK_POLICY_VALID', 'CAPITAL_RISK_POLICY_INVALID'],
            ['capital_policy_identity_match', $policyAvailable && $candidateAvailable, $policyAvailable && $candidateAvailable ? $policyIdentity : null, 'CAPITAL_POLICY_IDENTITY_MATCH', 'CAPITAL_RISK_IDENTITY_MISMATCH'],
            ['currency_match', $contextAvailable && $policyAvailable, $contextAvailable && $policyAvailable ? $currencyMatch : null, 'CAPITAL_RISK_CURRENCY_MATCH', 'CAPITAL_RISK_CURRENCY_MISMATCH'],
            ['gross_loss_per_unit_available', $actionRiskAvailable, $actionRiskAvailable ? $grossLossAvailable : null, 'GROSS_LOSS_PER_UNIT_AVAILABLE', 'GROSS_LOSS_PER_UNIT_REQUIRED'],
        ];
        foreach ($checks as [$name, $evaluated, $passed, $passCode, $failCode]) {
            $gates[] = $this->gate($name, $evaluated, $passed, $passed === true ? 'passed' : 'blocking', $passed === true ? $passCode : $failCode);
            if ($passed === false) $this->add($codes, $failCode);
        }

        $eligible = $candidateAvailable && $candidateReady && $supportedIntent && $actionRiskEvaluated && $riskIdentity && $referencePlanAvailable && $referenceIdentity && $contextValid && $policyValid && $policyIdentity && $currencyMatch && $grossLossAvailable;
        $maximumLoss = null;
        $capitalBase = $contextAvailable ? (float) ($capitalContext['capital_base']['amount'] ?? 0) : null;
        $pct = $policyAvailable && ($policy['maximum_loss_pct'] ?? null) !== null ? (float) $policy['maximum_loss_pct'] : null;
        if ($contextValid && $policyValid) {
            $maximumLoss = $this->maximumLossAmount($capitalBase, $policy);
        }
        $budgetValid = is_numeric($maximumLoss) && $maximumLoss > 0;
        $gates[] = $this->gate('policy_calculation', $contextValid && $policyValid, ($contextValid && $policyValid) ? $budgetValid : null, $budgetValid ? 'passed' : 'blocking', $budgetValid ? 'CAPITAL_RISK_REFERENCE_EVALUATED' : 'CAPITAL_RISK_POLICY_INVALID');
        $gates[] = $this->gate('risk_budget_validation', $contextValid && $policyValid, ($contextValid && $policyValid) ? $budgetValid : null, $budgetValid ? 'passed' : 'blocking', $budgetValid ? 'RISK_BUDGET_VALID' : 'CAPITAL_RISK_POLICY_INVALID');
        if ($contextValid && $policyValid && ! $budgetValid) $this->add($codes, 'CAPITAL_RISK_POLICY_INVALID');
        $gates[] = $this->gate('non_executable_capability', true, true, 'passed', 'CAPITAL_RISK_NON_EXECUTABLE_REFERENCE');

        $status = $eligible && $budgetValid ? 'evaluated_reference' : ($contextAvailable || $policyAvailable || $actionRiskAvailable ? 'unavailable' : 'unavailable');
        $eligibility = $status === 'evaluated_reference' ? 'evaluated_reference' : $this->eligibility($candidate, $actionRisk, $referencePlan, $capitalContext, $policy, $grossLossAvailable);
        if ($status === 'evaluated_reference') $this->add($codes, 'CAPITAL_RISK_REFERENCE_EVALUATED');
        $this->add($codes, 'NET_CAPITAL_RISK_UNAVAILABLE');
        $this->add($codes, 'PORTFOLIO_RISK_NOT_IMPLEMENTED');
        $this->add($codes, 'CAPITAL_RISK_NON_EXECUTABLE_REFERENCE');

        $result = [
            'schema_version' => $this->config['capital_risk_schema_version'],
            'status' => $status,
            'candidate_id' => $status === 'evaluated_reference' ? $candidateId : ($candidateId ?: null),
            'candidate_intent' => $candidate['intent'] ?? null,
            'evaluation_scope' => 'single_candidate_gross_capital_reference',
            'eligibility' => $eligibility,
            'capital_snapshot' => $contextValid ? ['schema_version'=>$capitalContext['schema_version'],'status'=>$capitalContext['status'],'capital_scope'=>$capitalContext['capital_scope'],'capital_base'=>$capitalContext['capital_base'],'as_of'=>$capitalContext['as_of'],'source'=>$capitalContext['source'],'approved_for_execution'=>false,'synthetic_test_only'=>(bool)($capitalContext['synthetic_test_only']??false)] : null,
            'policy_snapshot' => $policyValid ? ['schema_version'=>$policy['schema_version'],'status'=>$policy['status'],'method'=>$policy['method'],'maximum_loss_pct'=>$policy['maximum_loss_pct'] ?? null,'maximum_loss_amount'=>$policy['maximum_loss_amount'] ?? null,'currency'=>$policy['currency'],'candidate_id'=>$policy['candidate_id'] ?? null,'candidate_intent'=>$policy['candidate_intent'] ?? null,'policy_version'=>$policy['policy_version'] ?? null,'source'=>$policy['source'],'approved_for_execution'=>false,'synthetic_test_only'=>(bool)($policy['synthetic_test_only']??false)] : null,
            'metrics' => ['capital_base'=>$status === 'evaluated_reference' ? $capitalBase : null,'maximum_loss_pct'=>$status === 'evaluated_reference' ? $pct : null,'maximum_loss_amount'=>$status === 'evaluated_reference' ? round($maximumLoss, $this->precision()) : null,'gross_loss_per_unit'=>$status === 'evaluated_reference' ? (float) $grossLoss : null,'gross_reference_units'=>null,'gross_capital_at_risk'=>null,'net_capital_at_risk'=>null,'portfolio_exposure_after_entry'=>null],
            'limitations' => ['net_capital_risk_unavailable','portfolio_risk_not_implemented'],
            'reason_codes' => $this->ordered($codes),
            'calculation' => ['method'=>'capital_risk_contract_v1','calculated_at'=>$decisionAt],
            'metadata' => ['non_executable'=>true,'currency'=>$contextValid ? $capitalContext['capital_base']['currency'] : null],
            'capital_risk_gates' => $this->sortGates($gates),
        ];
        $this->validateCapitalRisk($result);
        return $result;
    }

    public function validateCapitalContext(array $context, ?string $decisionAt = null): void { if (! $this->validCapitalContext($context, $decisionAt)) throw new \InvalidArgumentException('invalid capital context'); }
    public function validateCapitalPolicy(array $policy): void { if (! $this->validPolicy($policy)) throw new \InvalidArgumentException('invalid capital policy'); }
    public function validateCapitalRisk(array $risk): void
    {
        if (($risk['schema_version'] ?? null) !== $this->config['capital_risk_schema_version']) throw new \InvalidArgumentException('invalid capital risk schema');
        if (! in_array($risk['status'] ?? null, ['unavailable','blocked','policy_ready','evaluated_reference','invalid'], true)) throw new \InvalidArgumentException('invalid capital risk status');
        if (($risk['metrics']['net_capital_at_risk'] ?? null) !== null || ($risk['metrics']['portfolio_exposure_after_entry'] ?? null) !== null) throw new \InvalidArgumentException('net/portfolio risk unavailable');
        if (($risk['metadata']['non_executable'] ?? null) !== true) throw new \InvalidArgumentException('capital risk must be non executable');
        if (count($risk['reason_codes']) !== count(array_unique($risk['reason_codes']))) throw new \InvalidArgumentException('duplicate capital risk reason');
    }

    protected function validCapitalContext(?array $context, ?string $decisionAt): bool
    {
        if (! is_array($context)) return false;
        if (($context['schema_version'] ?? null) !== $this->config['capital_context_schema_version']) return false;
        if (($context['status'] ?? null) !== 'reference_only') return false;
        if (! in_array($context['capital_scope'] ?? null, $this->config['supported_capital_scopes'], true)) return false;
        if (! is_numeric($context['capital_base']['amount'] ?? null) || (float) $context['capital_base']['amount'] <= 0) return false;
        if (empty($context['capital_base']['currency']) || empty($context['as_of']) || empty($context['source'])) return false;
        if (($context['approved_for_execution'] ?? null) !== false) return false;
        return $this->fresh($context['as_of'], $decisionAt);
    }

    protected function validPolicy(?array $policy): bool
    {
        if (! is_array($policy)) return false;
        if (($policy['schema_version'] ?? null) !== $this->config['capital_risk_policy_schema_version']) return false;
        if (($policy['status'] ?? null) !== 'reference_only') return false;
        if (! in_array($policy['method'] ?? null, $this->config['supported_policy_methods'], true)) return false;
        if (empty($policy['currency']) || empty($policy['source']) || ($policy['approved_for_execution'] ?? null) !== false) return false;
        $pct = $policy['maximum_loss_pct'] ?? null;
        $amount = $policy['maximum_loss_amount'] ?? null;
        if ($pct === null && $amount === null) return false;
        if ($pct !== null && (! is_numeric($pct) || (float) $pct <= 0 || (float) $pct > (float) $this->config['max_policy_loss_pct_ceiling'])) return false;
        if ($amount !== null && (! is_numeric($amount) || (float) $amount <= 0)) return false;
        return true;
    }

    protected function maximumLossAmount(float $capitalBase, array $policy): ?float
    {
        $pct = $policy['maximum_loss_pct'] ?? null;
        $amount = $policy['maximum_loss_amount'] ?? null;
        if ($pct !== null && $amount !== null) {
            $computed = $capitalBase * ((float) $pct) / 100;
            return abs($computed - (float) $amount) <= (float) $this->config['reconciliation_tolerance'] ? (float) $amount : null;
        }
        if ($pct !== null) return $capitalBase * ((float) $pct) / 100;
        return $amount !== null ? (float) $amount : null;
    }

    protected function eligibility(?array $candidate, ?array $actionRisk, ?array $referencePlan, ?array $context, ?array $policy, bool $grossLoss): string
    {
        if (! is_array($candidate)) return 'candidate_not_available';
        if (($candidate['status'] ?? null) !== 'candidate_ready') return 'candidate_not_ready';
        if (! is_array($actionRisk)) return 'action_risk_unavailable';
        if (($actionRisk['status'] ?? null) !== 'evaluated') return 'action_risk_not_evaluated';
        if (! is_array($referencePlan) || ! in_array($referencePlan['status'] ?? null, ['parameter_ready','materialized'], true)) return 'reference_plan_unavailable';
        if (! is_array($context)) return 'capital_context_unavailable';
        if (! is_array($policy)) return 'capital_policy_unavailable';
        if (! $grossLoss) return 'gross_loss_per_unit_unavailable';
        return 'invalid';
    }

    protected function fresh(?string $asOf, ?string $decisionAt): bool { if (! $asOf || ! $decisionAt) return false; try { $as=Carbon::parse($asOf); $dec=Carbon::parse($decisionAt); } catch (\Throwable) { return false; } return $as->lessThanOrEqualTo($dec) && $as->greaterThanOrEqualTo($dec->copy()->subMinutes($this->config['timestamp_freshness_minutes'])); }
    protected function precision(): int { return (int) ($this->config['calculation_precision'] ?? 6); }
    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes, string $code): void { if (! in_array($code, $codes, true)) $codes[] = $code; }
    protected function ordered(array $codes): array { sort($codes); return array_values(array_unique($codes)); }
    protected function sortGates(array $gates): array { $order = array_flip($this->config['capital_risk_gate_order']); usort($gates, fn($a,$b)=>($order[$a['gate']]??999)<=>($order[$b['gate']]??999)); return $gates; }
}
