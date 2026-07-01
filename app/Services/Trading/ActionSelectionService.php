<?php

namespace App\Services\Trading;

class ActionSelectionService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_action');
    }

    public function select(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $confidence = $context['trade_action_confidence'] ?? [];
        $risk = $context['decision_risk'] ?? [];
        $plan = $context['trade_plan'] ?? [];
        $safetyAction = $context['safety_action'] ?? 'WAIT';
        $portfolioApproval = $context['portfolio_approval'] ?? [];
        $reasonCodes = [];
        $warnings = [];
        $blockers = [];
        $gates = [];

        $available = is_array($candidate) && ($candidate['status'] ?? null) === 'candidate_ready';
        $gates[] = $this->gate('candidate_availability', true, $available, $available ? 'passed' : 'blocking', $available ? 'ACTION_CANDIDATE_READY' : 'ACTION_SELECTION_CANDIDATE_UNAVAILABLE');
        if (! $available) $this->add($reasonCodes, $blockers, ($candidate['status'] ?? null) === 'invalid' ? 'ACTION_SELECTION_CANDIDATE_INVALID' : (($candidate['status'] ?? null) === 'blocked' ? 'ACTION_SELECTION_CANDIDATE_BLOCKED' : 'ACTION_SELECTION_CANDIDATE_UNAVAILABLE'));

        $schemaOk = ($candidate['schema_version'] ?? null) === $this->config['schema_version'];
        $gates[] = $this->gate('candidate_schema_validity', $candidate !== null, $candidate !== null ? $schemaOk : null, $schemaOk ? 'passed' : 'blocking', $schemaOk ? 'CANDIDATE_SCHEMA_VALID' : 'ACTION_SELECTION_CANDIDATE_INVALID');
        $identityOk = $available && ! empty($candidate['candidate_id']);
        $gates[] = $this->gate('candidate_identity_validity', $candidate !== null, $candidate !== null ? $identityOk : null, $identityOk ? 'passed' : 'blocking', $identityOk ? 'CANDIDATE_ID_VALID' : 'SELECTED_CANDIDATE_UNAVAILABLE');
        $gates[] = $this->gate('candidate_ticker_consistency', $candidate !== null, $candidate !== null ? true : null, 'passed', 'CANDIDATE_TICKER_CONSISTENT');
        $gates[] = $this->gate('candidate_scope_consistency', $candidate !== null, $candidate !== null ? true : null, 'passed', 'CANDIDATE_SCOPE_CONSISTENT');
        $positionOk = ($candidate['metadata']['position_context'] ?? null) !== 'invalid_open_trade';
        $gates[] = $this->gate('candidate_position_context_consistency', $candidate !== null, $candidate !== null ? $positionOk : null, $positionOk ? 'passed' : 'blocking', $positionOk ? 'POSITION_CONTEXT_CONSISTENT' : 'ACTION_SELECTION_CANDIDATE_INVALID');

        $evidenceReady = ($candidate['eligibility'] ?? null) === 'eligible_for_risk_evaluation';
        $gates[] = $this->gate('evidence_readiness', $candidate !== null, $candidate !== null ? $evidenceReady : null, $evidenceReady ? 'passed' : 'blocking', $evidenceReady ? 'CANDIDATE_ELIGIBLE_FOR_RISK_EVALUATION' : 'ACTION_SELECTION_CANDIDATE_BLOCKED');

        $confidenceAvailable = ($confidence['status'] ?? null) === 'candidate_ready' && ($confidence['score'] ?? null) !== null;
        $gates[] = $this->gate('trade_action_confidence_availability', $available, $available ? $confidenceAvailable : null, $confidenceAvailable ? 'passed' : 'blocking', $confidenceAvailable ? 'ACTION_CONFIDENCE_AVAILABLE' : 'ACTION_SELECTION_CONFIDENCE_UNAVAILABLE');
        if ($available && ! $confidenceAvailable) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_CONFIDENCE_UNAVAILABLE');
        $confidenceMatch = $confidenceAvailable && ($confidence['action_candidate_id'] ?? null) === ($candidate['candidate_id'] ?? null) && ($confidence['action'] ?? null) === ($candidate['intent'] ?? null);
        $gates[] = $this->gate('trade_action_confidence_identity_match', $available, $available ? $confidenceMatch : null, $confidenceMatch ? 'passed' : 'blocking', $confidenceMatch ? 'CONFIDENCE_IDENTITY_MATCH' : 'ACTION_SELECTION_CONFIDENCE_IDENTITY_MISMATCH');
        if ($available && $confidenceAvailable && ! $confidenceMatch) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_CONFIDENCE_IDENTITY_MISMATCH');

        $riskAvailable = ($risk['status'] ?? null) === 'available';
        $gates[] = $this->gate('decision_risk_availability', $available, $available ? $riskAvailable : null, $riskAvailable ? 'passed' : 'blocking', $riskAvailable ? 'DECISION_RISK_AVAILABLE' : 'ACTION_SELECTION_RISK_UNAVAILABLE');
        if ($available && ! $riskAvailable) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_RISK_UNAVAILABLE');
        $riskMatch = $riskAvailable && ($risk['action_candidate_id'] ?? null) === ($candidate['candidate_id'] ?? null);
        $gates[] = $this->gate('decision_risk_identity_match', $available, $available ? $riskMatch : null, $riskMatch ? 'passed' : 'blocking', $riskMatch ? 'RISK_IDENTITY_MATCH' : 'ACTION_SELECTION_RISK_IDENTITY_MISMATCH');
        if ($available && $riskAvailable && ! $riskMatch) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_RISK_IDENTITY_MISMATCH');

        $planAvailable = ($plan['status'] ?? null) === 'available';
        $gates[] = $this->gate('trade_plan_availability', $available, $available ? $planAvailable : null, $planAvailable ? 'passed' : 'blocking', $planAvailable ? 'TRADE_PLAN_AVAILABLE' : 'ACTION_SELECTION_TRADE_PLAN_UNAVAILABLE');
        if ($available && ! $planAvailable) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_TRADE_PLAN_UNAVAILABLE');
        $planMatch = $planAvailable && ($plan['action_candidate_id'] ?? null) === ($candidate['candidate_id'] ?? null);
        $gates[] = $this->gate('trade_plan_identity_match', $available, $available ? $planMatch : null, $planMatch ? 'passed' : 'blocking', $planMatch ? 'PLAN_IDENTITY_MATCH' : 'ACTION_SELECTION_TRADE_PLAN_IDENTITY_MISMATCH');
        if ($available && $planAvailable && ! $planMatch) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_TRADE_PLAN_IDENTITY_MISMATCH');

        $approvalStatus = $portfolioApproval['status'] ?? 'unavailable';
        $productionApproved = ($portfolioApproval['approval_result']['production_approved'] ?? false) === true;
        $approvalOk = $productionApproved;
        $gates[] = $this->gate('portfolio_approval_availability', true, is_array($portfolioApproval) && $approvalStatus !== 'unavailable', $approvalStatus !== 'unavailable' ? 'passed' : 'blocking', $approvalStatus !== 'unavailable' ? 'PORTFOLIO_APPROVAL_AVAILABLE' : 'PORTFOLIO_APPROVAL_UNAVAILABLE');
        $gates[] = $this->gate('portfolio_production_approval', true, $approvalOk, $approvalOk ? 'passed' : 'blocking', $approvalOk ? 'PORTFOLIO_APPROVAL_PRODUCTION_AVAILABLE' : 'PORTFOLIO_APPROVAL_PRODUCTION_NOT_IMPLEMENTED');
        if (! $approvalOk) $this->add($reasonCodes, $blockers, match ($approvalStatus) {
            'eligible_for_reference_approval' => 'PORTFOLIO_APPROVAL_AUTHORIZATION_REQUIRED',
            'approved_reference' => 'PORTFOLIO_APPROVAL_PRODUCTION_NOT_IMPLEMENTED',
            'denied_reference' => 'PORTFOLIO_APPROVAL_DENIED_REFERENCE',
            default => 'PORTFOLIO_APPROVAL_UNAVAILABLE',
        });

        $capability = ($this->config['selection_capability'] ?? 'disabled') === 'enabled';
        $gates[] = $this->gate('capability_support', true, $capability, $capability ? 'passed' : 'blocking', $capability ? 'ACTION_SELECTION_CAPABILITY_AVAILABLE' : 'ACTION_SELECTION_CAPABILITY_DISABLED');
        if (! $capability) $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_CAPABILITY_DISABLED');
        $integrityOk = $blockers === [];
        $gates[] = $this->gate('integrity_blockers', true, $integrityOk, $integrityOk ? 'passed' : 'blocking', $integrityOk ? 'NO_SELECTION_BLOCKERS' : 'SELECTED_CANDIDATE_UNAVAILABLE');
        $policy = false;
        $gates[] = $this->gate('selection_policy_availability', true, $policy, 'blocking', 'ACTION_SELECTION_POLICY_NOT_IMPLEMENTED');
        $this->add($reasonCodes, $blockers, 'ACTION_SELECTION_POLICY_NOT_IMPLEMENTED');

        $status = ! $candidate ? 'candidate_unavailable' : (!$available ? (($candidate['status'] ?? null) === 'invalid' ? 'invalid' : 'candidate_not_ready') : 'eligible_but_selection_disabled');
        $eligibility = ! $candidate ? 'ineligible' : (!$available ? (($candidate['eligibility'] ?? null) === 'research_only' ? 'research_only' : 'blocked') : 'eligible_but_not_selectable');
        if ($available) $this->add($reasonCodes, $warnings, 'CANDIDATE_ELIGIBLE_BUT_NOT_SELECTABLE');
        $this->add($reasonCodes, $warnings, $safetyAction === 'NO_TRADE' ? 'SAFETY_ACTION_NO_TRADE_SELECTED' : 'SAFETY_ACTION_WAIT_SELECTED');

        $result = [
            'schema_version' => $this->config['selection_schema_version'],
            'status' => $status,
            'candidate_available' => $available,
            'candidate_id' => $available ? $candidate['candidate_id'] : null,
            'candidate_intent' => $available ? $candidate['intent'] : null,
            'selection_eligibility' => $eligibility,
            'selection_stage' => 'selection_policy',
            'safety_action' => $safetyAction,
            'selected_candidate' => null,
            'selection_gates' => $this->sortGates($gates, 'selection_gate_order'),
            'reason_codes' => $this->orderedCodes($reasonCodes),
            'warnings' => $this->orderedCodes($warnings),
            'blockers' => $this->orderedCodes($blockers),
            'metadata' => ['selection_capability' => $this->config['selection_capability']],
        ];
        $this->validateSelection($result);
        return $result;
    }

    public function validateSelection(array $selection): void
    {
        if (($selection['schema_version'] ?? null) !== $this->config['selection_schema_version']) throw new \InvalidArgumentException('invalid selection schema');
        if (! in_array($selection['status'] ?? null, $this->config['selection_statuses'], true)) throw new \InvalidArgumentException('invalid selection status');
        if (! in_array($selection['selection_eligibility'] ?? null, $this->config['selection_eligibility'], true)) throw new \InvalidArgumentException('invalid selection eligibility');
        if (($selection['selected_candidate'] ?? null) !== null) throw new \InvalidArgumentException('selected candidate disabled in sprint 10.1');
        if (! in_array($selection['safety_action'] ?? null, ['WAIT','NO_TRADE'], true)) throw new \InvalidArgumentException('invalid safety action');
        if (count($selection['reason_codes'] ?? []) !== count(array_unique($selection['reason_codes'] ?? []))) throw new \InvalidArgumentException('duplicate selection reason');
        foreach ($selection['selection_gates'] ?? [] as $gate) foreach (['gate','evaluated','passed','severity','code','details'] as $key) if (! array_key_exists($key, $gate)) throw new \InvalidArgumentException('invalid selection gate');
    }

    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details = []): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes, array &$target, string $code): void { $codes[] = $code; $target[] = $code; }
    protected function sortGates(array $gates, string $key): array { $order = array_flip($this->config[$key]); usort($gates, fn($a,$b) => ($order[$a['gate']] ?? 999) <=> ($order[$b['gate']] ?? 999)); return $gates; }
    protected function orderedCodes(array $codes): array { $codes = array_values(array_unique($codes)); $order = array_flip($this->config['reason_codes']); usort($codes, fn($a,$b) => ($order[$a] ?? 999) <=> ($order[$b] ?? 999) ?: strcmp($a,$b)); return $codes; }
}
