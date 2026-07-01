<?php

namespace App\Services\Trading;

class ActionPromotionService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_action');
    }

    public function promote(array $context): array
    {
        $selection = $context['selection'];
        $safetyAction = $selection['safety_action'] ?? 'WAIT';
        $selected = $selection['selected_candidate'] ?? null;
        $reasonCodes = [];
        $warnings = [];
        $blockers = [];
        $gates = [];

        $selectedAvailable = $selected !== null;
        $gates[] = $this->gate('selected_candidate_availability', true, $selectedAvailable, $selectedAvailable ? 'passed' : 'blocking', $selectedAvailable ? 'SELECTED_CANDIDATE_AVAILABLE' : 'ACTION_PROMOTION_SELECTED_CANDIDATE_REQUIRED');
        if (! $selectedAvailable) $this->add($reasonCodes, $blockers, 'ACTION_PROMOTION_SELECTED_CANDIDATE_REQUIRED');
        $gates[] = $this->gate('selected_candidate_identity', $selectedAvailable, $selectedAvailable ? ! empty($selected['candidate_id']) : null, $selectedAvailable ? 'passed' : 'not_applicable', $selectedAvailable ? 'SELECTED_CANDIDATE_ID_VALID' : 'ACTION_PROMOTION_NOT_APPLICABLE');
        $capability = ($this->config['promotion_capability'] ?? 'disabled') === 'enabled';
        $gates[] = $this->gate('promotion_capability', true, $capability, $capability ? 'passed' : 'blocking', $capability ? 'ACTION_PROMOTION_CAPABILITY_AVAILABLE' : 'ACTION_PROMOTION_CAPABILITY_DISABLED');
        if (! $capability) $this->add($reasonCodes, $blockers, 'ACTION_PROMOTION_CAPABILITY_DISABLED');
        $gates[] = $this->gate('promotion_policy', true, false, 'blocking', 'ACTION_PROMOTION_POLICY_NOT_IMPLEMENTED');
        $this->add($reasonCodes, $blockers, 'ACTION_PROMOTION_POLICY_NOT_IMPLEMENTED');
        foreach (['risk_availability','trade_plan_availability','execution_capability','safety_policy'] as $gate) {
            $code = $gate === 'execution_capability' ? 'EXECUTION_CAPABILITY_NOT_IMPLEMENTED' : ($gate === 'safety_policy' ? 'SAFETY_POLICY_ACTIVE' : strtoupper($gate).'_BLOCKED');
            $gates[] = $this->gate($gate, true, $gate === 'safety_policy' ? true : false, $gate === 'safety_policy' ? 'passed' : 'blocking', $code);
        }
        $this->add($reasonCodes, $blockers, 'PROMOTED_ACTION_UNAVAILABLE');
        $this->add($reasonCodes, $blockers, 'EXECUTABLE_ACTION_UNAVAILABLE');
        $this->add($reasonCodes, $blockers, 'EXECUTION_CAPABILITY_NOT_IMPLEMENTED');

        $status = $selectedAvailable ? 'eligible_but_disabled' : 'not_promoted';
        $eligibility = $selectedAvailable ? 'eligible_but_disabled' : 'selected_candidate_required';
        $result = [
            'schema_version' => $this->config['promotion_schema_version'],
            'status' => $status,
            'selected_candidate_available' => $selectedAvailable,
            'selected_candidate_id' => $selected['candidate_id'] ?? null,
            'candidate_intent' => $selected['intent'] ?? null,
            'promotion_eligibility' => $eligibility,
            'safety_action' => $safetyAction,
            'promoted_action' => null,
            'executable_action' => null,
            'execution_readiness' => 'unavailable',
            'promotion_gates' => $this->sortGates($gates),
            'reason_codes' => $this->orderedCodes($reasonCodes),
            'warnings' => $this->orderedCodes($warnings),
            'blockers' => $this->orderedCodes($blockers),
            'metadata' => ['promotion_capability' => $this->config['promotion_capability']],
        ];
        $this->validatePromotion($result);
        return $result;
    }

    public function validatePromotion(array $promotion): void
    {
        if (($promotion['schema_version'] ?? null) !== $this->config['promotion_schema_version']) throw new \InvalidArgumentException('invalid promotion schema');
        if (! in_array($promotion['status'] ?? null, $this->config['promotion_statuses'], true)) throw new \InvalidArgumentException('invalid promotion status');
        if (! in_array($promotion['promotion_eligibility'] ?? null, $this->config['promotion_eligibility'], true)) throw new \InvalidArgumentException('invalid promotion eligibility');
        if (($promotion['promoted_action'] ?? null) !== null || ($promotion['executable_action'] ?? null) !== null) throw new \InvalidArgumentException('promotion disabled in sprint 10.1');
        if (! in_array($promotion['safety_action'] ?? null, ['WAIT','NO_TRADE'], true)) throw new \InvalidArgumentException('invalid safety action');
        foreach ($promotion['promotion_gates'] ?? [] as $gate) foreach (['gate','evaluated','passed','severity','code','details'] as $key) if (! array_key_exists($key, $gate)) throw new \InvalidArgumentException('invalid promotion gate');
    }

    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details = []): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes, array &$target, string $code): void { $codes[] = $code; $target[] = $code; }
    protected function sortGates(array $gates): array { $order = array_flip($this->config['promotion_gate_order']); usort($gates, fn($a,$b) => ($order[$a['gate']] ?? 999) <=> ($order[$b['gate']] ?? 999)); return $gates; }
    protected function orderedCodes(array $codes): array { $codes = array_values(array_unique($codes)); $order = array_flip($this->config['reason_codes']); usort($codes, fn($a,$b) => ($order[$a] ?? 999) <=> ($order[$b] ?? 999) ?: strcmp($a,$b)); return $codes; }
}
