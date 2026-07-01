<?php

namespace App\Services\Trading;

class RiskEngineService
{
    public function __construct(protected ?array $config = null, protected ?ActionRiskEvaluationService $actionRiskService = null, protected ?CapitalRiskEvaluationService $capitalRiskService = null, protected ?PositionSizingService $positionSizingService = null, protected ?ExposureAggregationService $exposureAggregationService = null, protected ?PortfolioRiskEvaluationService $portfolioRiskService = null)
    {
        $this->config ??= config('trading_risk');
        $this->actionRiskService ??= new ActionRiskEvaluationService($this->config);
        $this->capitalRiskService ??= new CapitalRiskEvaluationService();
        $this->positionSizingService ??= new PositionSizingService();
        $this->exposureAggregationService ??= new ExposureAggregationService();
        $this->portfolioRiskService ??= new PortfolioRiskEvaluationService();
        $this->validateConfig($this->config);
    }

    public function assess(array $context): array
    {
        $artifactAvailability = $context['artifact_availability'] ?? [];
        $actionCandidate = $context['action_candidate'] ?? null;
        $reasonCodes = [];
        $research = $this->researchRiskEvidence($artifactAvailability, $reasonCodes);
        $actionRisk = $this->actionRiskService->evaluate([
            'decision_at' => $context['decision_at'],
            'action_candidate' => $actionCandidate,
            'selected_parameters' => $context['selected_parameters'] ?? null,
            'entry_reference' => $context['entry_reference'] ?? null,
        ]);
        $decision = $this->decisionRiskFromActionRisk($actionRisk, $actionCandidate);
        $capitalRisk = $this->capitalRiskService->evaluate([
            'decision_at' => $context['decision_at'],
            'action_candidate' => $actionCandidate,
            'action_risk' => $actionRisk,
            'reference_plan' => $context['reference_plan'] ?? null,
            'capital_context' => $context['capital_context'] ?? null,
            'capital_risk_policy' => $context['capital_risk_policy'] ?? null,
        ]);
        $positionSizing = $this->positionSizingService->size([
            'action_candidate' => $actionCandidate,
            'capital_risk' => $capitalRisk,
            'action_risk' => $actionRisk,
            'reference_plan' => $context['reference_plan'] ?? null,
        ]);
        $exposureAggregation = $this->exposureAggregationService->aggregate([
            'decision_at' => $context['decision_at'],
            'portfolio_context' => $context['portfolio_context'] ?? null,
            'position_snapshots' => $context['position_snapshots'] ?? null,
        ]);
        $portfolioRisk = $this->portfolioRiskService->evaluate([
            'action_candidate' => $actionCandidate,
            'capital_risk' => $capitalRisk,
            'position_sizing' => $positionSizing,
            'execution_readiness' => $context['execution_readiness'] ?? null,
            'portfolio_context' => $context['portfolio_context'] ?? null,
            'exposure_aggregation' => $exposureAggregation,
            'portfolio_risk_policy' => $context['portfolio_risk_policy'] ?? null,
            'candidate_ticker' => $context['ticker'] ?? ($actionCandidate['metadata']['ticker'] ?? null),
            'candidate_sector' => $context['candidate_sector'] ?? null,
        ]);

        $status = $research['status'] === 'invalid' ? 'invalid' : $research['status'];
        $result = [
            'schema_version' => $this->config['risk_schema_version'],
            'status' => $status,
            'research_risk_evidence' => $research,
            'action_specific_risk' => $actionRisk,
            'decision_risk' => $decision,
            'capital_risk' => $capitalRisk,
            'position_sizing' => $positionSizing,
            'exposure_aggregation' => $exposureAggregation,
            'portfolio_risk' => $portfolioRisk,
            'reason_codes' => $this->orderedReasonCodes(array_values(array_unique(array_merge($reasonCodes, $actionRisk['reason_codes'], $decision['reason_codes'], $capitalRisk['reason_codes'], $positionSizing['reason_codes'], $exposureAggregation['reason_codes'], $portfolioRisk['reason_codes'])))),
            'calculation' => [
                'method' => 'risk_contract_v1_3',
                'calculated_at' => $context['decision_at'],
            ],
        ];

        $this->validateRisk($result);
        return $result;
    }

    public function validateConfig(array $config): void
    {
        foreach (['risk_schema_version','trade_plan_schema_version','research_risk_required_artifacts','decision_risk_required_artifacts','supported_risk_metric_keys'] as $key) {
            if (! array_key_exists($key, $config)) throw new \InvalidArgumentException("missing {$key}");
        }
        if (! str_starts_with($config['risk_schema_version'], 'trading_risk_')) throw new \InvalidArgumentException('invalid risk schema version');
        if (($config['action_specific_required'] ?? null) !== true) throw new \InvalidArgumentException('action-specific risk is required');
        foreach (array_merge($config['research_risk_required_artifacts'], $config['decision_risk_required_artifacts']) as $type) {
            if (! in_array($type, $config['allowed_artifact_types'], true)) throw new \InvalidArgumentException('unknown artifact type');
        }
        if (! in_array($config['position_sizing_capability_status'], ['not_implemented'], true)) throw new \InvalidArgumentException('invalid position sizing capability');
        foreach ($config['supported_risk_metric_keys'] as $metric) {
            if (! in_array($metric, ['expected_return_pct','expected_loss_pct','risk_reward_ratio','probability_tp_hit','probability_sl_hit','expected_drawdown_pct','cvar_pct','holding_days'], true)) throw new \InvalidArgumentException('unsupported metric key');
        }
    }

    public function validateRisk(array $risk): void
    {
        if (($risk['schema_version'] ?? null) !== $this->config['risk_schema_version']) throw new \InvalidArgumentException('invalid risk schema');
        if (! in_array($risk['status'] ?? null, $this->config['statuses'], true)) throw new \InvalidArgumentException('invalid risk status');
        $this->actionRiskService->validateActionRisk($risk['action_specific_risk']);
        if (($risk['decision_risk']['status'] ?? null) === 'unavailable') {
            foreach ($this->decisionMetricKeys() as $key) {
                if (($risk['decision_risk'][$key] ?? null) !== null) throw new \InvalidArgumentException('unavailable decision risk metric must be null');
            }
            if (($risk['decision_risk']['action'] ?? null) === null && (($risk['decision_risk']['entry_price'] ?? null) !== null)) throw new \InvalidArgumentException('action identity required for entry price');
        }
        if (($risk['position_sizing']['status'] ?? null) === 'not_implemented') {
            foreach (['recommended_fraction','recommended_quantity','maximum_loss_amount'] as $key) {
                if (($risk['position_sizing'][$key] ?? null) !== null) throw new \InvalidArgumentException('position sizing output must be null');
            }
        }
    }

    protected function decisionRiskFromActionRisk(array $actionRisk, ?array $actionCandidate): array
    {
        return [
            'status' => 'unavailable',
            'action' => $actionRisk['candidate_intent'],
            'action_candidate_id' => $actionRisk['candidate_id'],
            'action_candidate_version' => ($actionCandidate['status'] ?? null) === 'candidate_ready' ? $actionCandidate['candidate_version'] : null,
            'action_candidate_eligibility' => $actionCandidate['eligibility'] ?? null,
            'entry_price' => null,
            'take_profit' => null,
            'stop_loss' => null,
            'eligibility' => $actionRisk['eligibility'],
            'reason_codes' => $this->orderedReasonCodes($actionRisk['reason_codes']),
            'expected_return_pct' => null,
            'expected_loss_pct' => null,
            'risk_reward_ratio' => null,
            'probability_tp_hit' => null,
            'probability_sl_hit' => null,
            'expected_drawdown_pct' => null,
            'cvar_pct' => null,
            'holding_days' => null,
        ];
    }

    protected function researchRiskEvidence(array $artifactAvailability, array &$reasonCodes): array
    {
        $sources = [];
        $limitations = [];
        $warnings = [];
        $available = 0;
        $invalid = false;

        foreach ($this->config['research_risk_required_artifacts'] as $type) {
            $artifact = $artifactAvailability[$type] ?? [];
            if ($artifact !== [] && ($artifact['latest_valid_available'] ?? false)) {
                $available++;
                $sources[] = $this->source($type, $artifact);
            }
            foreach ($artifact['warnings'] ?? [] as $warning) {
                $limitations[] = $warning;
                if (str_contains($warning, 'high_unclassified_rate')) $reasonCodes[] = 'HIGH_UNCLASSIFIED_RATE';
                if (str_contains($warning, 'ATR family unavailable')) $reasonCodes[] = 'ATR_FAMILY_UNAVAILABLE';
                if (str_contains($warning, 'extreme_winner_dependency')) $reasonCodes[] = 'EXTREME_WINNER_DEPENDENCY';
            }
            if (($artifact['quality_grade'] ?? null) === 'limited') $limitations[] = $type.'_limited_quality';
            if (($artifact['is_stale'] ?? false)) { $warnings[] = 'stale_'.$type; $reasonCodes[] = 'RISK_ARTIFACT_STALE'; }
            if (($artifact['is_quarantined'] ?? false)) { $invalid = true; $reasonCodes[] = 'RISK_ARTIFACT_QUARANTINED'; }
            foreach (($artifact['dependency_status'] ?? []) as $status) {
                if ($status !== 'resolved' && in_array($status, $this->config['dependency_blocker_statuses'], true)) {
                    $reasonCodes[] = 'RISK_DEPENDENCY_UNRESOLVED';
                    $warnings[] = 'dependency_'.$status.'_'.$type;
                    if (in_array($status, ['checksum_mismatch', 'schema_mismatch', 'ticker_mismatch'], true)) $invalid = true;
                }
            }
        }

        $required = count($this->config['research_risk_required_artifacts']);
        $status = $invalid ? 'invalid' : ($available === 0 ? 'unavailable' : ($available < $required ? 'partial' : 'research_only'));
        $reasonCodes[] = $status === 'research_only' ? 'RESEARCH_RISK_EVIDENCE_AVAILABLE' : 'RESEARCH_RISK_EVIDENCE_PARTIAL';

        return [
            'status' => $status,
            'source_artifacts' => $sources,
            'metrics' => [
                'cvar_available' => false,
                'downside_metric_available' => false,
                'oos_expectancy_available' => false,
                'confidence_interval_available' => false,
                'profitable_fold_available' => false,
            ],
            'limitations' => array_values(array_unique($limitations)),
            'warnings' => array_values(array_unique($warnings)),
        ];
    }

    protected function decisionRisk(array $artifactAvailability, ?array $actionCandidate, array &$reasonCodes): array
    {
        $codes = ['DECISION_RISK_UNAVAILABLE'];
        if ($actionCandidate === null || ($actionCandidate['status'] ?? null) !== 'candidate_ready') $codes[] = 'ACTION_CANDIDATE_NOT_AVAILABLE';
        if ($actionCandidate !== null && empty($actionCandidate['intent'])) $codes[] = 'DECISION_RISK_NOT_ACTION_SPECIFIC';

        foreach (['tp_optimizer' => ['DECISION_USABLE_TP_UNAVAILABLE','SELECTED_TP_REQUIRED_FOR_RISK'], 'sl_optimizer' => ['DECISION_USABLE_SL_UNAVAILABLE','SELECTED_SL_REQUIRED_FOR_RISK']] as $type => [$decisionCode, $selectedCode]) {
            $artifact = $artifactAvailability[$type] ?? [];
            if (! ($artifact['latest_decision_available'] ?? false)) $codes[] = $decisionCode;
            if (! ($artifact['selected_available'] ?? false)) $codes[] = $selectedCode;
            if (($artifact['is_stale'] ?? false)) $codes[] = 'RISK_ARTIFACT_STALE';
            if (($artifact['is_quarantined'] ?? false)) $codes[] = 'RISK_ARTIFACT_QUARANTINED';
            foreach (($artifact['dependency_status'] ?? []) as $status) {
                if (in_array($status, $this->config['dependency_blocker_statuses'], true) && $status !== 'resolved') $codes[] = 'RISK_DEPENDENCY_UNRESOLVED';
            }
        }
        $codes[] = 'RISK_METRICS_INCOMPLETE';
        $reasonCodes = array_merge($reasonCodes, $codes);

        return array_merge([
            'status' => 'unavailable',
            'action' => ($actionCandidate['status'] ?? null) === 'candidate_ready' ? $actionCandidate['intent'] : null,
            'action_candidate_id' => ($actionCandidate['status'] ?? null) === 'candidate_ready' ? $actionCandidate['candidate_id'] : null,
            'action_candidate_version' => ($actionCandidate['status'] ?? null) === 'candidate_ready' ? $actionCandidate['candidate_version'] : null,
            'action_candidate_eligibility' => $actionCandidate['eligibility'] ?? null,
            'entry_price' => null,
            'take_profit' => null,
            'stop_loss' => null,
            'eligibility' => ($actionCandidate['status'] ?? null) === 'candidate_ready' ? 'risk_metrics_incomplete' : 'action_candidate_not_available',
            'reason_codes' => $this->orderedReasonCodes(array_values(array_unique($codes))),
        ], array_fill_keys($this->decisionMetricKeys(), null));
    }

    protected function source(string $type, array $artifact): array
    {
        return [
            'artifact_type' => $type,
            'registry_artifact_id' => $artifact['latest_valid']['id'] ?? null,
            'schema_version' => $artifact['latest_valid']['schema_version'] ?? null,
            'usage_tier' => $artifact['latest_valid']['usage_tier'] ?? null,
            'quality_grade' => $artifact['quality_grade'] ?? null,
            'selected_available' => (bool) ($artifact['selected_available'] ?? false),
            'stale' => (bool) ($artifact['is_stale'] ?? false),
            'quarantined' => (bool) ($artifact['is_quarantined'] ?? false),
            'dependency_status' => $artifact['dependency_status'] ?? [],
        ];
    }

    protected function decisionMetricKeys(): array
    {
        return ['expected_return_pct','expected_loss_pct','risk_reward_ratio','probability_tp_hit','probability_sl_hit','expected_drawdown_pct','cvar_pct','holding_days'];
    }

    protected function orderedReasonCodes(array $codes): array
    {
        $order = ['RESEARCH_RISK_EVIDENCE_AVAILABLE','RESEARCH_RISK_EVIDENCE_PARTIAL','DECISION_RISK_UNAVAILABLE','ACTION_CANDIDATE_NOT_AVAILABLE','DECISION_USABLE_TP_UNAVAILABLE','DECISION_USABLE_SL_UNAVAILABLE','SELECTED_TP_REQUIRED_FOR_RISK','SELECTED_SL_REQUIRED_FOR_RISK','RISK_METRICS_INCOMPLETE','RISK_ARTIFACT_STALE','RISK_ARTIFACT_QUARANTINED','RISK_DEPENDENCY_UNRESOLVED','POSITION_SIZING_NOT_IMPLEMENTED','DECISION_RISK_NOT_ACTION_SPECIFIC','HIGH_UNCLASSIFIED_RATE','ATR_FAMILY_UNAVAILABLE','EXTREME_WINNER_DEPENDENCY'];
        usort($codes, fn($a, $b) => (array_search($a, $order, true) === false ? 999 : array_search($a, $order, true)) <=> (array_search($b, $order, true) === false ? 999 : array_search($b, $order, true)) ?: strcmp($a, $b));
        return $codes;
    }
}
