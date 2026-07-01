<?php

namespace App\Services\Trading;

class ActionRiskEvaluationService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_risk');
    }

    public function evaluate(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $parameters = $context['selected_parameters'] ?? null;
        $decisionAt = $context['decision_at'] ?? null;
        $entryReference = $context['entry_reference'] ?? null;
        $codes = [];
        $warnings = [];
        $limitations = [];
        $gates = [];

        $candidateAvailable = is_array($candidate);
        $gates[] = $this->gate('candidate_available', true, $candidateAvailable, $candidateAvailable ? 'passed' : 'blocking', $candidateAvailable ? 'ACTION_CANDIDATE_READY' : 'ACTION_RISK_CANDIDATE_REQUIRED');
        if (! $candidateAvailable) $this->add($codes, 'ACTION_RISK_CANDIDATE_REQUIRED');
        $candidateSchema = ($candidate['schema_version'] ?? null) === config('trading_action.schema_version');
        $gates[] = $this->gate('candidate_schema_valid', $candidateAvailable, $candidateAvailable ? $candidateSchema : null, $candidateSchema ? 'passed' : 'blocking', $candidateSchema ? 'CANDIDATE_SCHEMA_VALID' : 'ACTION_RISK_CANDIDATE_REQUIRED');
        $candidateReady = ($candidate['status'] ?? null) === 'candidate_ready';
        $gates[] = $this->gate('candidate_status_ready', $candidateAvailable, $candidateAvailable ? $candidateReady : null, $candidateReady ? 'passed' : 'blocking', $candidateReady ? 'CANDIDATE_READY' : 'ACTION_RISK_CANDIDATE_NOT_READY');
        if ($candidateAvailable && ! $candidateReady) $this->add($codes, 'ACTION_RISK_CANDIDATE_NOT_READY');
        $supportedIntent = in_array($candidate['intent'] ?? null, $this->config['supported_action_risk_intents'], true);
        $gates[] = $this->gate('supported_intent', $candidateAvailable, $candidateAvailable ? $supportedIntent : null, $supportedIntent ? 'passed' : 'blocking', $supportedIntent ? 'ACTION_RISK_INTENT_SUPPORTED' : 'ACTION_RISK_UNSUPPORTED_INTENT');
        if ($candidateAvailable && ! $supportedIntent) $this->add($codes, 'ACTION_RISK_UNSUPPORTED_INTENT');
        $candidateIdentity = ! empty($candidate['candidate_id'] ?? null);
        $gates[] = $this->gate('candidate_identity', $candidateAvailable, $candidateAvailable ? $candidateIdentity : null, $candidateIdentity ? 'passed' : 'blocking', $candidateIdentity ? 'CANDIDATE_ID_VALID' : 'ACTION_RISK_CANDIDATE_REQUIRED');

        $paramAvailable = is_array($parameters);
        $gates[] = $this->gate('parameter_evidence_available', true, $paramAvailable, $paramAvailable ? 'passed' : 'blocking', $paramAvailable ? 'PARAMETER_EVIDENCE_AVAILABLE' : 'ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED');
        if (! $paramAvailable) $this->add($codes, 'ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED');
        $paramSchema = ($parameters['schema_version'] ?? null) === $this->config['selected_parameters_schema_version'];
        $gates[] = $this->gate('parameter_schema_valid', $paramAvailable, $paramAvailable ? $paramSchema : null, $paramSchema ? 'passed' : 'blocking', $paramSchema ? 'PARAMETER_SCHEMA_VALID' : 'ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED');
        $tickerMatch = ($parameters['ticker'] ?? null) === ($candidate['metadata']['ticker'] ?? null);
        $gates[] = $this->gate('ticker_identity_match', $paramAvailable && $candidateAvailable, ($paramAvailable && $candidateAvailable) ? $tickerMatch : null, $tickerMatch ? 'passed' : 'blocking', $tickerMatch ? 'TICKER_MATCH' : 'ACTION_RISK_IDENTITY_MISMATCH');
        $candidateMatch = ($parameters['candidate_id'] ?? null) === ($candidate['candidate_id'] ?? null) && ($parameters['candidate_intent'] ?? null) === ($candidate['intent'] ?? null);
        $gates[] = $this->gate('candidate_identity_match', $paramAvailable && $candidateAvailable, ($paramAvailable && $candidateAvailable) ? $candidateMatch : null, $candidateMatch ? 'passed' : 'blocking', $candidateMatch ? 'CANDIDATE_MATCH' : 'ACTION_RISK_IDENTITY_MISMATCH');
        if ($paramAvailable && $candidateAvailable && (! $tickerMatch || ! $candidateMatch)) $this->add($codes, 'ACTION_RISK_IDENTITY_MISMATCH');

        foreach (['take_profit' => ['tp_decision_usability','ACTION_RISK_TP_DECISION_USABLE_REQUIRED','selected_tp_available','ACTION_RISK_SELECTED_TP_REQUIRED'], 'stop_loss' => ['sl_decision_usability','ACTION_RISK_SL_DECISION_USABLE_REQUIRED','selected_sl_available','ACTION_RISK_SELECTED_SL_REQUIRED']] as $key => [$usageGate, $usageCode, $selectedGate, $selectedCode]) {
            $source = $parameters[$key]['source_artifact'] ?? [];
            $decisionUsable = ($source['usage_tier'] ?? null) === 'decision_usable';
            $selected = (bool) ($parameters[$key]['selected'] ?? false);
            $gates[] = $this->gate($usageGate, $paramAvailable, $paramAvailable ? $decisionUsable : null, $decisionUsable ? 'passed' : 'blocking', $decisionUsable ? strtoupper($key).'_DECISION_USABLE' : $usageCode);
            if ($paramAvailable && ! $decisionUsable) $this->add($codes, ($source['usage_tier'] ?? null) === 'research_only' ? 'ACTION_RISK_PARAMETER_EVIDENCE_RESEARCH_ONLY' : $usageCode);
            $gates[] = $this->gate($selectedGate, $paramAvailable, $paramAvailable ? $selected : null, $selected ? 'passed' : 'blocking', $selected ? strtoupper($key).'_SELECTED' : $selectedCode);
            if ($paramAvailable && ! $selected) $this->add($codes, $selectedCode);
        }

        $checksumOk = $this->sourceOk($parameters, fn($s) => ! empty($s['checksum'] ?? null));
        $depsOk = $this->sourceOk($parameters, fn($s) => collect($s['dependency_status'] ?? ['resolved'])->every(fn($v) => $v === 'resolved'));
        $staleOk = $this->sourceOk($parameters, fn($s) => ! ($s['stale'] ?? false));
        $quarantineOk = $this->sourceOk($parameters, fn($s) => ! ($s['quarantined'] ?? false));
        foreach ([['source_checksum_available',$checksumOk,'ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED'],['dependency_resolved',$depsOk,'ACTION_RISK_DEPENDENCY_UNRESOLVED'],['source_not_stale',$staleOk,'ACTION_RISK_SOURCE_STALE'],['source_not_quarantined',$quarantineOk,'ACTION_RISK_SOURCE_QUARANTINED']] as [$gate, $ok, $code]) {
            $gates[] = $this->gate($gate, $paramAvailable, $paramAvailable ? $ok : null, $ok ? 'passed' : 'blocking', $ok ? strtoupper($gate).'_OK' : $code);
            if ($paramAvailable && ! $ok) $this->add($codes, $code);
        }

        $supportedType = $this->parameterSupported($parameters, 'take_profit') && $this->parameterSupported($parameters, 'stop_loss');
        $numericValid = $this->numericValue($parameters, 'take_profit') > 0 && $this->numericValue($parameters, 'stop_loss') > 0;
        $gates[] = $this->gate('supported_parameter_type', $paramAvailable, $paramAvailable ? $supportedType : null, $supportedType ? 'passed' : 'blocking', $supportedType ? 'PARAMETER_TYPE_SUPPORTED' : 'ACTION_RISK_PARAMETER_TYPE_UNSUPPORTED');
        if ($paramAvailable && ! $supportedType) $this->add($codes, 'ACTION_RISK_PARAMETER_TYPE_UNSUPPORTED');
        $gates[] = $this->gate('numeric_parameter_validity', $paramAvailable, $paramAvailable ? $numericValid : null, $numericValid ? 'passed' : 'blocking', $numericValid ? 'PARAMETER_NUMERIC_VALID' : 'ACTION_RISK_PARAMETER_INVALID');
        if ($paramAvailable && ! $numericValid) $this->add($codes, 'ACTION_RISK_PARAMETER_INVALID');

        $eligible = $candidateReady && $supportedIntent && $candidateIdentity && $paramAvailable && $paramSchema && $tickerMatch && $candidateMatch && $checksumOk && $depsOk && $staleOk && $quarantineOk && $supportedType && $numericValid;
        $metrics = $this->nullMetrics();
        $parameterSnapshot = null;
        if ($eligible) {
            $tp = $this->numericValue($parameters, 'take_profit');
            $sl = abs($this->numericValue($parameters, 'stop_loss'));
            $rr = round($tp / $sl, $this->config['rounding_precision']);
            $metrics['take_profit_pct'] = round($tp, $this->config['rounding_precision']);
            $metrics['stop_loss_pct'] = round($sl, $this->config['rounding_precision']);
            $metrics['gross_upside_pct'] = round($tp, $this->config['rounding_precision']);
            $metrics['gross_downside_pct'] = round($sl, $this->config['rounding_precision']);
            $metrics['gross_reward_risk_ratio'] = $rr;
            if (is_array($entryReference) && is_numeric($entryReference['price'] ?? null) && (float) $entryReference['price'] > 0) {
                $entry = (float) $entryReference['price'];
                $tpPrice = round($entry * (1 + $tp / 100), $this->config['rounding_precision']);
                $slPrice = round($entry * (1 - $sl / 100), $this->config['rounding_precision']);
                $metrics['entry_price'] = $entry;
                $metrics['take_profit_price'] = $tpPrice;
                $metrics['stop_loss_price'] = $slPrice;
                $metrics['gross_profit_per_unit'] = round($tpPrice - $entry, $this->config['rounding_precision']);
                $metrics['gross_loss_per_unit'] = round($entry - $slPrice, $this->config['rounding_precision']);
                $warnings[] = 'ACTION_RISK_NON_EXECUTABLE_REFERENCE';
                $this->add($codes, 'ACTION_RISK_NON_EXECUTABLE_REFERENCE');
            }
            $this->add($codes, 'ACTION_RISK_GROSS_GEOMETRY_AVAILABLE');
            $parameterSnapshot = $parameters;
        }
        foreach (['ACTION_RISK_NET_METRICS_UNAVAILABLE','ACTION_RISK_PROBABILITY_METRICS_UNAVAILABLE','ACTION_RISK_CAPITAL_METRICS_UNAVAILABLE'] as $code) $this->add($codes, $code);
        $gates[] = $this->gate('geometry_calculation', $paramAvailable && $candidateAvailable, ($paramAvailable && $candidateAvailable) ? $eligible : null, $eligible ? 'passed' : 'blocking', $eligible ? 'ACTION_RISK_GROSS_GEOMETRY_AVAILABLE' : 'ACTION_RISK_UNAVAILABLE');

        $status = $eligible ? 'evaluated' : ($candidateAvailable && $paramAvailable ? 'blocked' : 'unavailable');
        $eligibility = $eligible ? 'evaluated' : $this->eligibility($candidate, $parameters, $codes);
        $result = ['schema_version'=>$this->config['action_risk_schema_version'],'status'=>$status,'candidate_id'=>$eligible ? $candidate['candidate_id'] : ($candidate['candidate_id'] ?? null),'candidate_intent'=>$candidate['intent'] ?? null,'evaluation_scope'=>'action_specific_gross_geometry','eligibility'=>$eligibility,'parameter_snapshot'=>$parameterSnapshot,'metrics'=>$metrics,'limitations'=>array_values(array_unique($limitations)),'warnings'=>array_values(array_unique($warnings)),'reason_codes'=>$this->orderedCodes($codes),'gates'=>$this->sortGates($gates),'calculation'=>['method'=>$this->config['action_risk_calculation_method'],'calculated_at'=>$decisionAt],'metadata'=>['non_executable'=>true,'synthetic_test_only'=>(bool)($parameters['synthetic_test_only'] ?? false)]];
        $this->validateActionRisk($result);
        return $result;
    }

    public function validateActionRisk(array $risk): void
    {
        if (($risk['schema_version'] ?? null) !== $this->config['action_risk_schema_version']) throw new \InvalidArgumentException('invalid action risk schema');
        if (! in_array($risk['status'] ?? null, ['unavailable','blocked','parameter_ready','evaluated','invalid'], true)) throw new \InvalidArgumentException('invalid action risk status');
        if (($risk['status'] ?? null) !== 'evaluated' && ($risk['metrics']['gross_reward_risk_ratio'] ?? null) !== null) throw new \InvalidArgumentException('unavailable action risk metric must be null');
        if (($risk['status'] ?? null) === 'evaluated') {
            if (empty($risk['candidate_id']) || empty($risk['parameter_snapshot'])) throw new \InvalidArgumentException('evaluated action risk requires candidate and parameters');
            $up = $risk['metrics']['gross_upside_pct']; $down = $risk['metrics']['gross_downside_pct']; $rr = $risk['metrics']['gross_reward_risk_ratio'];
            if ($down <= 0 || round($up / $down, $this->config['rounding_precision']) !== $rr) throw new \InvalidArgumentException('invalid gross geometry');
        }
        foreach (['probability_of_profit','expected_return_pct','expected_loss_pct','expected_value_pct','cvar_pct','net_reward_risk_ratio'] as $key) if (($risk['metrics'][$key] ?? null) !== null) throw new \InvalidArgumentException('unsupported metric must be null');
    }

    protected function nullMetrics(): array { return ['take_profit_pct'=>null,'stop_loss_pct'=>null,'gross_upside_pct'=>null,'gross_downside_pct'=>null,'gross_reward_risk_ratio'=>null,'entry_price'=>null,'take_profit_price'=>null,'stop_loss_price'=>null,'gross_profit_per_unit'=>null,'gross_loss_per_unit'=>null,'net_reward_risk_ratio'=>null,'probability_of_profit'=>null,'expected_return_pct'=>null,'expected_loss_pct'=>null,'expected_value_pct'=>null,'cvar_pct'=>null]; }
    protected function sourceOk(?array $p, callable $fn): bool { if (! is_array($p)) return false; return $fn($p['take_profit']['source_artifact'] ?? []) && $fn($p['stop_loss']['source_artifact'] ?? []); }
    protected function parameterSupported(?array $p, string $key): bool { return is_array($p) && in_array($p[$key]['parameter_type'] ?? null, $this->config['supported_parameter_types'], true) && in_array($p[$key]['unit'] ?? null, $this->config['supported_units'], true); }
    protected function numericValue(?array $p, string $key): float { return is_numeric($p[$key]['value'] ?? null) ? (float)$p[$key]['value'] : 0.0; }
    protected function eligibility(?array $c, ?array $p, array $codes): string { if (! is_array($c)) return 'candidate_not_available'; if (($c['status'] ?? null) !== 'candidate_ready') return 'candidate_not_ready'; if (! is_array($p)) return 'parameter_evidence_unavailable'; if (in_array('ACTION_RISK_PARAMETER_EVIDENCE_RESEARCH_ONLY', $codes, true)) return 'parameter_evidence_research_only'; if (in_array('ACTION_RISK_IDENTITY_MISMATCH', $codes, true)) return 'identity_mismatch'; if (in_array('ACTION_RISK_PARAMETER_INVALID', $codes, true)) return 'invalid'; return 'integrity_blocked'; }
    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes, string $code): void { $codes[] = $code; }
    protected function sortGates(array $gates): array { $order = array_flip($this->config['action_risk_gate_order']); usort($gates, fn($a,$b) => ($order[$a['gate']] ?? 999) <=> ($order[$b['gate']] ?? 999)); return $gates; }
    protected function orderedCodes(array $codes): array { $codes = array_values(array_unique($codes)); $order = ['ACTION_RISK_UNAVAILABLE','ACTION_RISK_CANDIDATE_REQUIRED','ACTION_RISK_CANDIDATE_NOT_READY','ACTION_RISK_UNSUPPORTED_INTENT','ACTION_RISK_PARAMETER_EVIDENCE_REQUIRED','ACTION_RISK_PARAMETER_EVIDENCE_RESEARCH_ONLY','ACTION_RISK_TP_DECISION_USABLE_REQUIRED','ACTION_RISK_SL_DECISION_USABLE_REQUIRED','ACTION_RISK_SELECTED_TP_REQUIRED','ACTION_RISK_SELECTED_SL_REQUIRED','ACTION_RISK_IDENTITY_MISMATCH','ACTION_RISK_DEPENDENCY_UNRESOLVED','ACTION_RISK_SOURCE_STALE','ACTION_RISK_SOURCE_QUARANTINED','ACTION_RISK_PARAMETER_TYPE_UNSUPPORTED','ACTION_RISK_PARAMETER_INVALID','ACTION_RISK_GROSS_GEOMETRY_AVAILABLE','ACTION_RISK_NET_METRICS_UNAVAILABLE','ACTION_RISK_PROBABILITY_METRICS_UNAVAILABLE','ACTION_RISK_CAPITAL_METRICS_UNAVAILABLE','ACTION_RISK_NON_EXECUTABLE_REFERENCE']; usort($codes, fn($a,$b) => (array_search($a,$order,true)===false?999:array_search($a,$order,true)) <=> (array_search($b,$order,true)===false?999:array_search($b,$order,true)) ?: strcmp($a,$b)); return $codes; }
}
