<?php

namespace App\Services\Trading;

class ActionCandidateService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_action');
    }

    public function build(array $context): array
    {
        $ticker = $context['ticker'];
        $predictions = $context['prediction_snapshots'] ?? [];
        $predictionEvidence = $context['prediction_evidence'] ?? [];
        $artifacts = $context['artifact_availability'] ?? [];
        $positionContext = $context['position_context'] ?? 'unknown';
        $evidenceReadiness = $context['evidence_readiness'] ?? 'unavailable';
        $decisionSeed = $context['decision_fingerprint_seed'] ?? '';
        $reasonCodes = [];
        $blockers = [];
        $warnings = [];
        $gates = [];

        $inputValid = in_array($positionContext, $this->config['supported_position_contexts'], true);
        $gates[] = $this->gate('input_validity', true, $inputValid, $inputValid ? 'passed' : 'blocking', $inputValid ? 'INPUT_VALID' : 'ACTION_CANDIDATE_INVALID');
        if (! $inputValid) $this->add($reasonCodes, $blockers, 'ACTION_CANDIDATE_INVALID');

        if ($positionContext === 'invalid_open_trade') {
            $gates[] = $this->gate('position_context_eligibility', true, false, 'blocking', 'ACTION_CANDIDATE_INVALID');
            $gates = array_merge($gates, $this->skippedGatesAfter('position_context_eligibility'));
            return $this->result('invalid', null, null, 'invalid', null, $gates, $predictions, $artifacts, $reasonCodes, $warnings, $blockers, $ticker, $positionContext, $decisionSeed);
        }

        if ($positionContext === 'open_trade') {
            $gates[] = $this->gate('position_context_eligibility', true, false, 'blocking', 'POSITION_MANAGEMENT_CANDIDATE_NOT_IMPLEMENTED');
            $this->add($reasonCodes, $blockers, 'POSITION_MANAGEMENT_CANDIDATE_NOT_IMPLEMENTED');
            $gates = array_merge($gates, $this->skippedGatesAfter('position_context_eligibility'));
            return $this->result('blocked', 'position_management', null, 'blocked', null, $gates, $predictions, $artifacts, $reasonCodes, $warnings, $blockers, $ticker, $positionContext, $decisionSeed);
        }

        $gates[] = $this->gate('position_context_eligibility', true, true, 'passed', 'POSITION_CONTEXT_ELIGIBLE');
        $directional = collect($predictions)->where('semantic_role', 'directional')->values();
        $directionalUp = $directional->contains(fn($p) => ($p['normalized_semantic'] ?? null) === 'directional_up');
        $directionalDown = $directional->contains(fn($p) => ($p['normalized_semantic'] ?? null) === 'directional_down');
        $directionalAvailable = $directional->isNotEmpty();
        $conflict = ($predictionEvidence['conflict_status'] ?? 'none') === 'conflicting';
        $fresh = collect($predictions)->every(fn($p) => ($p['freshness_status'] ?? null) === 'fresh');

        $gates[] = $this->gate('directional_prediction_availability', true, $directionalAvailable, $directionalAvailable ? 'passed' : 'blocking', $directionalAvailable ? 'DIRECTIONAL_PREDICTION_AVAILABLE' : 'LONG_ENTRY_CANDIDATE_REQUIRES_DIRECTIONAL_UP');
        if (! $directionalAvailable) $this->add($reasonCodes, $blockers, 'LONG_ENTRY_CANDIDATE_REQUIRES_DIRECTIONAL_UP');
        $gates[] = $this->gate('prediction_consistency', true, ! $conflict, $conflict ? 'blocking' : 'passed', $conflict ? 'PREDICTION_CONFLICT' : 'PREDICTION_CONSISTENT');
        if ($conflict) $this->add($reasonCodes, $blockers, 'PREDICTION_CONFLICT');
        $gates[] = $this->gate('prediction_freshness', true, $fresh, $fresh ? 'passed' : 'blocking', $fresh ? 'PREDICTION_FRESH' : 'PREDICTION_STALE');
        if (! $fresh) $this->add($reasonCodes, $blockers, 'PREDICTION_STALE');
        if ($directionalDown || ($directionalAvailable && ! $directionalUp)) $this->add($reasonCodes, $blockers, 'DIRECTIONAL_SIGNAL_NOT_ELIGIBLE');

        $decisionReady = $evidenceReadiness === 'decision_ready';
        $gates[] = $this->gate('evidence_readiness', true, $decisionReady, $decisionReady ? 'passed' : 'blocking', $decisionReady ? 'EVIDENCE_DECISION_READY' : 'DECISION_READY_EVIDENCE_REQUIRED');
        if (! $decisionReady) $this->add($reasonCodes, $warnings, 'DECISION_READY_EVIDENCE_REQUIRED');

        foreach (['tp_optimizer' => ['decision_usable_tp_availability','DECISION_USABLE_TP_REQUIRED_FOR_CANDIDATE','selected_tp_availability','SELECTED_TP_REQUIRED_FOR_CANDIDATE'], 'sl_optimizer' => ['decision_usable_sl_availability','DECISION_USABLE_SL_REQUIRED_FOR_CANDIDATE','selected_sl_availability','SELECTED_SL_REQUIRED_FOR_CANDIDATE']] as $type => [$decisionGate, $decisionCode, $selectedGate, $selectedCode]) {
            $decisionAvailable = (bool) ($artifacts[$type]['latest_decision_available'] ?? false);
            $selectedAvailable = (bool) ($artifacts[$type]['selected_available'] ?? false);
            $gates[] = $this->gate($decisionGate, true, $decisionAvailable, $decisionAvailable ? 'passed' : 'blocking', $decisionAvailable ? strtoupper($type).'_DECISION_USABLE' : $decisionCode);
            if (! $decisionAvailable) $this->add($reasonCodes, $blockers, $decisionCode);
            $gates[] = $this->gate($selectedGate, true, $selectedAvailable, $selectedAvailable ? 'passed' : 'blocking', $selectedAvailable ? strtoupper($type).'_SELECTED' : $selectedCode);
            if (! $selectedAvailable) $this->add($reasonCodes, $blockers, $selectedCode);
        }

        $dependencyOk = $staleOk = $quarantineOk = true;
        foreach (['tp_optimizer','sl_optimizer'] as $type) {
            $artifact = $artifacts[$type] ?? [];
            if ($artifact['is_stale'] ?? false) $staleOk = false;
            if ($artifact['is_quarantined'] ?? false) $quarantineOk = false;
            foreach (($artifact['dependency_status'] ?? []) as $status) if ($status !== 'resolved') $dependencyOk = false;
        }
        $gates[] = $this->gate('artifact_integrity', true, $dependencyOk && $staleOk && $quarantineOk, ($dependencyOk && $staleOk && $quarantineOk) ? 'passed' : 'blocking', ($dependencyOk && $staleOk && $quarantineOk) ? 'ARTIFACT_INTEGRITY_OK' : 'ACTION_CANDIDATE_BLOCKED');
        $gates[] = $this->gate('dependency_resolution', true, $dependencyOk, $dependencyOk ? 'passed' : 'blocking', $dependencyOk ? 'DEPENDENCIES_OK' : 'RISK_DEPENDENCY_UNRESOLVED');
        $gates[] = $this->gate('staleness', true, $staleOk, $staleOk ? 'passed' : 'blocking', $staleOk ? 'NOT_STALE' : 'RISK_ARTIFACT_STALE');
        $gates[] = $this->gate('quarantine', true, $quarantineOk, $quarantineOk ? 'passed' : 'blocking', $quarantineOk ? 'NOT_QUARANTINED' : 'RISK_ARTIFACT_QUARANTINED');
        $gates[] = $this->gate('candidate_capability', true, true, 'passed', 'ACTION_CANDIDATE_CONTRACT_AVAILABLE');
        $gates[] = $this->gate('execution_capability', true, false, 'blocking', 'CANDIDATE_NOT_EXECUTABLE');
        $this->add($reasonCodes, $warnings, 'CANDIDATE_NOT_EXECUTABLE');

        $ready = $directionalUp && ! $conflict && $fresh && $decisionReady && $this->passed($gates, ['decision_usable_tp_availability','decision_usable_sl_availability','selected_tp_availability','selected_sl_availability','dependency_resolution','staleness','quarantine']);
        if ($ready) {
            $this->add($reasonCodes, $warnings, 'ACTION_CANDIDATE_READY');
            $this->add($reasonCodes, $warnings, 'CANDIDATE_ELIGIBLE_FOR_RISK_EVALUATION');
            $this->add($reasonCodes, $blockers, 'ACTION_CANDIDATE_AVAILABLE_NOT_PROMOTED');
            $this->add($reasonCodes, $blockers, 'ACTION_PROMOTION_NOT_IMPLEMENTED');
            return $this->result('candidate_ready', 'long_entry', 'long', 'eligible_for_risk_evaluation', $this->candidateId($ticker, 'long_entry', 'long', $positionContext, $predictions, $artifacts, $decisionSeed), $gates, $predictions, $artifacts, $reasonCodes, $warnings, $blockers, $ticker, $positionContext, $decisionSeed);
        }

        $status = $evidenceReadiness === 'research_ready' ? 'observation_only' : 'blocked';
        $eligibility = $evidenceReadiness === 'research_ready' ? 'research_only' : 'blocked';
        $this->add($reasonCodes, $warnings, $status === 'observation_only' ? 'ACTION_CANDIDATE_OBSERVATION_ONLY' : 'ACTION_CANDIDATE_BLOCKED');
        return $this->result($status, $status === 'observation_only' ? 'observation' : null, null, $eligibility, null, $gates, $predictions, $artifacts, $reasonCodes, $warnings, $blockers, $ticker, $positionContext, $decisionSeed);
    }

    public function promotion(?array $candidate): array
    {
        return ['status' => 'not_implemented', 'candidate_id' => $candidate['candidate_id'] ?? null, 'final_action' => null, 'reason_codes' => ['ACTION_PROMOTION_NOT_IMPLEMENTED']];
    }

    public function validateCandidate(array $candidate): void
    {
        if (($candidate['schema_version'] ?? null) !== $this->config['schema_version']) throw new \InvalidArgumentException('invalid action candidate schema');
        if (! in_array($candidate['status'] ?? null, $this->config['statuses'], true)) throw new \InvalidArgumentException('invalid candidate status');
        if (($candidate['intent'] ?? null) !== null && ! in_array($candidate['intent'], $this->config['supported_intents'], true)) throw new \InvalidArgumentException('invalid candidate intent');
        if (! in_array($candidate['eligibility'] ?? null, $this->config['eligibility'], true)) throw new \InvalidArgumentException('invalid candidate eligibility');
        if (($candidate['execution_status'] ?? null) !== $this->config['execution_status']) throw new \InvalidArgumentException('candidate must be non executable');
        if (($candidate['status'] ?? null) === 'candidate_ready' && (empty($candidate['candidate_id']) || empty($candidate['intent']))) throw new \InvalidArgumentException('candidate ready requires identity and intent');
        if (count($candidate['reason_codes'] ?? []) !== count(array_unique($candidate['reason_codes'] ?? []))) throw new \InvalidArgumentException('duplicate candidate reason code');
        foreach ($candidate['eligibility_gates'] ?? [] as $gate) foreach (['gate','evaluated','passed','severity','code','details'] as $key) if (! array_key_exists($key, $gate)) throw new \InvalidArgumentException('invalid candidate gate');
    }

    protected function result(string $status, ?string $intent, ?string $direction, string $eligibility, ?string $candidateId, array $gates, array $predictions, array $artifacts, array $reasonCodes, array $warnings, array $blockers, string $ticker, string $positionContext, string $decisionSeed): array
    {
        $result = [
            'schema_version' => $this->config['schema_version'],
            'status' => $status,
            'candidate_id' => $candidateId,
            'candidate_version' => $this->config['candidate_contract_version'],
            'intent' => $intent,
            'direction' => $direction,
            'position_effect' => $intent === 'long_entry' ? 'opens_position' : null,
            'execution_status' => $this->config['execution_status'],
            'eligibility' => $eligibility,
            'eligibility_gates' => $this->sortGates($gates),
            'prediction_basis' => ['snapshots' => $predictions],
            'artifact_basis' => ['source_artifacts' => $this->artifactBasis($artifacts)],
            'confidence_basis' => ['uses_score_threshold' => false],
            'risk_preconditions' => ['requires_action_identity' => true, 'candidate_id' => $candidateId],
            'trade_plan_preconditions' => ['requires_decision_risk' => true, 'requires_selected_tp_sl' => true],
            'reason_codes' => $this->orderedCodes($reasonCodes),
            'warnings' => $this->orderedCodes($warnings),
            'blockers' => $this->orderedCodes($blockers),
            'metadata' => ['ticker' => $ticker, 'position_context' => $positionContext, 'identity_seed_algorithm' => 'sha256', 'decision_fingerprint_seed' => $decisionSeed],
        ];
        $this->validateCandidate($result);
        return $result;
    }

    protected function candidateId(string $ticker, string $intent, string $direction, string $positionContext, array $predictions, array $artifacts, string $decisionSeed): string
    {
        $artifactIds = collect($artifacts)->map(fn($a) => ['id' => $a['latest_valid']['id'] ?? null, 'checksum' => $a['latest_valid']['checksum'] ?? null])->sortKeys()->all();
        $predictionIds = collect($predictions)->map(fn($p) => ['variant' => $p['variant'] ?? null, 'semantic_role' => $p['semantic_role'] ?? null, 'generated_at' => $p['generated_at'] ?? null, 'normalized_semantic' => $p['normalized_semantic'] ?? null])->sortBy(fn($p) => implode('|', $p))->values()->all();
        return hash('sha256', json_encode(compact('ticker','intent','direction','positionContext','predictionIds','artifactIds','decisionSeed') + ['candidate_contract_version' => $this->config['candidate_contract_version']], JSON_UNESCAPED_SLASHES));
    }

    protected function artifactBasis(array $artifacts): array { return collect($artifacts)->map(fn($a) => ['id' => $a['latest_valid']['id'] ?? null, 'checksum' => $a['latest_valid']['checksum'] ?? null, 'latest_decision_available' => $a['latest_decision_available'] ?? false, 'selected_available' => $a['selected_available'] ?? false])->all(); }
    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details = []): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes, array &$target, string $code): void { $codes[] = $code; $target[] = $code; }
    protected function skippedGatesAfter(string $after): array { $idx = array_search($after, $this->config['candidate_gate_order'], true); return collect(array_slice($this->config['candidate_gate_order'], $idx + 1))->map(fn($g) => $this->gate($g, false, null, 'not_applicable', 'GATE_SKIPPED'))->all(); }
    protected function sortGates(array $gates): array { $order = array_flip($this->config['candidate_gate_order']); usort($gates, fn($a, $b) => ($order[$a['gate']] ?? 999) <=> ($order[$b['gate']] ?? 999)); return $gates; }
    protected function passed(array $gates, array $names): bool { return collect($gates)->whereIn('gate', $names)->every(fn($g) => $g['passed'] === true); }
    protected function orderedCodes(array $codes): array { $codes = array_values(array_unique($codes)); $order = array_flip($this->config['reason_codes']); usort($codes, fn($a, $b) => ($order[$a] ?? 999) <=> ($order[$b] ?? 999) ?: strcmp($a, $b)); return $codes; }
}
