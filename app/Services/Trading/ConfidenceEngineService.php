<?php

namespace App\Services\Trading;

class ConfidenceEngineService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_confidence');
        $this->validateConfig($this->config);
    }

    public function calculate(array $context): array
    {
        $components = $this->components($context);
        $baseScore = round(array_sum(array_column($components, 'weighted_score')), 6);
        $penalties = $this->penalties($context);
        $penaltyTotal = round(array_sum(array_column($penalties, 'amount')), 6);
        $scoreAfterPenalties = max(0, $baseScore - $penaltyTotal);
        $caps = $this->caps($context);
        $appliedCap = null;
        $score = $scoreAfterPenalties;
        foreach ($caps as $cap) {
            if ($cap['applied']) {
                $score = min($score, $cap['maximum_score']);
                $appliedCap = $appliedCap ?? $cap;
            }
        }
        $score = round(max($this->config['scale']['min'], min($this->config['scale']['max'], $score)), 6);
        $status = $this->status($context);
        $actionConfidence = $this->actionConfidence($context, $score);

        return [
            'schema_version' => $this->config['schema_version'],
            'status' => $status,
            'evidence_confidence' => [
                'score' => $score,
                'scale_min' => $this->config['scale']['min'],
                'scale_max' => $this->config['scale']['max'],
                'grade' => $this->grade($score),
                'components' => array_values($components),
                'penalties' => $penalties,
                'caps' => $caps,
                'warnings' => $this->confidenceWarnings($context),
                'interpretation' => ['scope' => 'evidence_quality', 'does_not_mean' => ['probability_of_profit','probability_price_will_rise','buy_recommendation','expected_return']],
            ],
            'safety_decision_confidence' => $this->safetyConfidence($context),
            'trade_action_confidence' => $this->tradeActionConfidence($context),
            'action_confidence' => null,
            'capability' => [
                'level' => 'basic_with_confidence',
                'supported_actions' => ['WAIT','NO_TRADE'],
                'unsupported_actions' => ['BUY','ACCUMULATE','HOLD','SELL','CUT_LOSS','BUY_BACK'],
                'engines' => [
                    'confidence' => 'available',
                    'reason' => 'available',
                    'research_risk' => 'available',
                    'decision_risk' => 'contract_only',
                    'trade_plan' => 'contract_only',
                    'action_selection' => 'not_implemented',
                    'position_sizing' => 'not_implemented',
                    'position_management' => 'not_implemented',
                ],
            ],
            'calculation' => [
                'method' => $this->config['method'],
                'weight_profile' => $this->config['weight_profile'],
                'calculated_at' => $context['decision_at'],
                'base_weighted_score' => $baseScore,
                'penalty_total' => $penaltyTotal,
                'score_after_penalties' => round($scoreAfterPenalties, 6),
                'applied_cap' => $appliedCap,
                'final_score' => $score,
                'missing_component_policy' => 'retain_zero_contribution',
                'rounding_policy' => 'round_final_to_6_decimals',
            ],
        ];
    }

    public function validateConfig(array $config): void
    {
        $weights = $config['component_weights'] ?? [];
        if ($weights === []) throw new \InvalidArgumentException('missing component weights');
        foreach ($weights as $key => $weight) {
            if (! is_numeric($weight) || $weight < 0) throw new \InvalidArgumentException('invalid component weight');
        }
        if (abs(array_sum($weights) - 1.0) > 0.000001) throw new \InvalidArgumentException('component weights must sum to 1');
        $last = -1;
        foreach ($config['grade_thresholds'] as $grade => $threshold) {
            if ($threshold === null) continue;
            if ($threshold < $last) throw new \InvalidArgumentException('grade thresholds must be monotonic');
            $last = $threshold;
        }
    }

    protected function components(array $context): array
    {
        $weights = $this->config['component_weights'];
        $raw = [
            'prediction_availability' => $context['prediction_evidence']['quality_status'] === 'available' ? 100 : 0,
            'prediction_freshness' => collect($context['prediction_snapshots'])->every(fn($p) => $p['freshness_status'] === 'fresh') ? 100 : 25,
            'prediction_semantic_completeness' => $context['prediction_evidence']['directional_available'] ? 100 : ($context['prediction_evidence']['regime_available'] ? 55 : 0),
            'prediction_consistency' => $context['prediction_evidence']['conflict_status'] === 'none' ? 100 : 20,
            'research_artifact_coverage' => $this->artifactCoverage($context['artifact_availability'], 'latest_research_available'),
            'artifact_integrity' => $this->artifactIntegrityScore($context['artifact_availability']),
            'artifact_freshness' => collect($context['artifact_availability'])->contains(fn($a) => $a['is_stale'] ?? false) ? 40 : 100,
            'research_quality' => $this->researchQualityScore($context['artifact_availability']),
            'decision_parameter_readiness' => $context['evidence_readiness'] === 'decision_ready' ? 100 : 20,
        ];
        $components = [];
        foreach ($weights as $key => $weight) {
            $score = round($raw[$key] ?? 0, 6);
            $components[$key] = [
                'key' => $key,
                'status' => $this->componentStatus($score),
                'raw_score' => $score,
                'weight' => $weight,
                'weighted_score' => round($score * $weight, 6),
                'available' => true,
                'source_count' => $key === 'research_quality' ? count($context['artifact_availability']) : count($context['prediction_snapshots']),
                'reason_codes' => [],
                'evidence' => [],
                'warnings' => [],
                'availability_status' => 'available',
                'denominator' => 100,
                'missing_reason' => null,
                'handling_policy' => 'retain_zero_contribution',
            ];
        }
        return $components;
    }

    protected function penalties(array $context): array
    {
        $warnings = collect($context['reason_codes']);
        $map = [
            'HIGH_UNCLASSIFIED_RATE' => ['high_unclassified_rate', 'High unclassified rate.'],
            'ATR_FAMILY_UNAVAILABLE' => ['atr_unavailable', 'ATR family unavailable.'],
            'EXTREME_WINNER_DEPENDENCY' => ['extreme_winner_dependency', 'Extreme winner dependency.'],
            'SELECTED_TP_UNAVAILABLE' => ['selected_null', 'Selected TP unavailable.'],
            'DEPENDENCY_UNRESOLVED' => ['dependency_unresolved', 'Dependency unresolved.'],
        ];
        $penalties = [];
        foreach ($map as $code => [$key, $reason]) {
            if ($warnings->contains($code)) {
                $penalties[] = ['code' => $code, 'amount' => $this->config['penalties'][$key], 'applied' => true, 'reason' => $reason];
            }
        }
        return $penalties;
    }

    protected function caps(array $context): array
    {
        $codes = collect($context['reason_codes']);
        $capConfig = $this->config['caps'];
        return [
            ['code' => 'RESEARCH_ONLY_ACTION_CAP', 'maximum_score' => $capConfig['research_only_action_cap'], 'applied' => $context['evidence_readiness'] === 'research_ready', 'reason' => 'Decision-grade TP/SL artifacts are unavailable.'],
            ['code' => 'STALE_ARTIFACT_CAP', 'maximum_score' => $capConfig['stale_artifact_cap'], 'applied' => $codes->contains('ARTIFACT_STALE'), 'reason' => 'Stale artifact.'],
            ['code' => 'DEPENDENCY_MISMATCH_CAP', 'maximum_score' => $capConfig['dependency_mismatch_cap'], 'applied' => $codes->contains('DEPENDENCY_CHECKSUM_MISMATCH'), 'reason' => 'Dependency mismatch.'],
            ['code' => 'QUARANTINE_CAP', 'maximum_score' => $capConfig['quarantine_cap'], 'applied' => $codes->contains('ARTIFACT_QUARANTINED'), 'reason' => 'Quarantined artifact.'],
            ['code' => 'PREDICTION_CONFLICT_CAP', 'maximum_score' => $capConfig['prediction_conflict_cap'], 'applied' => $codes->contains('PREDICTION_CONFLICT'), 'reason' => 'Prediction conflict.'],
        ];
    }


    protected function safetyConfidence(array $context): array
    {
        $action = ($context['evidence_readiness'] === 'invalid' || $context['evidence_readiness'] === 'unavailable') ? 'NO_TRADE' : 'WAIT';
        $codes = array_values(array_intersect($context['reason_codes'], ['NO_DECISION_USABLE_TP','NO_DECISION_USABLE_SL','SELECTED_TP_UNAVAILABLE','SELECTED_SL_UNAVAILABLE','ACTION_CAPABILITY_NOT_IMPLEMENTED','ACTION_SELECTION_NOT_IMPLEMENTED','PREDICTION_STALE','PREDICTION_INVALID']));
        $score = $codes === [] ? 50.0 : min(95.0, 70.0 + count($codes) * 4.0);
        return ['action' => $action, 'score' => round($score, 6), 'status' => 'available', 'basis' => $action === 'WAIT' ? 'decision_artifacts_not_usable' : 'minimum_evidence_unavailable', 'component_codes' => $codes, 'contributing_blockers' => $codes, 'contributing_limitations' => array_values(array_intersect($context['reason_codes'], ['HIGH_UNCLASSIFIED_RATE','ATR_FAMILY_UNAVAILABLE','EXTREME_WINNER_DEPENDENCY'])), 'interpretation' => ['scope' => 'safety_decision_support', 'does_not_mean' => ['market_risk_is_low','trade_is_safe','profit_is_guaranteed']]];
    }

    protected function tradeActionConfidence(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        if (($candidate['status'] ?? null) === 'candidate_ready') {
            return [
                'action' => $candidate['intent'],
                'action_candidate_id' => $candidate['candidate_id'],
                'score' => null,
                'status' => 'candidate_ready',
                'eligibility' => $candidate['eligibility'],
                'reason_codes' => ['CANDIDATE_ELIGIBLE_FOR_RISK_EVALUATION', 'ACTION_PROMOTION_NOT_IMPLEMENTED'],
                'interpretation' => ['scope' => 'action_candidate_evidence', 'not_a_final_recommendation' => true],
            ];
        }
        return ['action' => null, 'score' => null, 'status' => 'unavailable', 'eligibility' => 'action_candidate_not_available', 'reason_codes' => ['ACTION_SELECTION_NOT_IMPLEMENTED']];
    }

    protected function actionConfidence(array $context, float $evidenceScore): array
    {
        $eligible = in_array($context['evidence_readiness'], $this->config['action_confidence']['eligible_readiness'], true)
            && in_array($context['action_eligibility'], $this->config['action_confidence']['eligible_action_eligibility'], true);
        if (! $eligible) {
            return ['score' => null, 'status' => 'unavailable', 'reason_codes' => array_values(array_intersect($context['reason_codes'], ['NO_DECISION_USABLE_TP', 'NO_DECISION_USABLE_SL', 'SELECTED_TP_UNAVAILABLE', 'SELECTED_SL_UNAVAILABLE']))];
        }
        return ['score' => $evidenceScore, 'status' => 'available', 'reason_codes' => []];
    }

    protected function status(array $context): string
    {
        return match ($context['evidence_readiness']) {
            'decision_ready' => 'decision_ready',
            'research_ready' => 'research_only',
            'partial' => 'partial',
            'invalid' => 'invalid',
            default => 'unavailable',
        };
    }

    protected function grade(float $score): string
    {
        $grade = 'very_low';
        foreach ($this->config['grade_thresholds'] as $name => $threshold) {
            if ($threshold !== null && $score >= $threshold) $grade = $name;
        }
        return $grade;
    }

    protected function artifactCoverage(array $availability, string $key): float
    {
        if ($availability === []) return 0;
        return round(collect($availability)->filter(fn($a) => $a[$key] ?? false)->count() / count($availability) * 100, 6);
    }

    protected function artifactIntegrityScore(array $availability): float
    {
        if ($availability === []) return 0;
        if (collect($availability)->contains(fn($a) => $a['is_quarantined'] ?? false)) return 10;
        if (collect($availability)->contains(fn($a) => in_array('checksum_mismatch', $a['dependency_status'] ?? [], true))) return 20;
        return 100;
    }

    protected function researchQualityScore(array $availability): float
    {
        if ($availability === []) return 0;
        return round(collect($availability)->avg(fn($a) => $this->config['quality_grade_scores'][$a['quality_grade'] ?? 'unknown'] ?? $this->config['quality_grade_scores']['unknown']), 6);
    }

    protected function componentStatus(float $score): string
    {
        return $score >= 80 ? 'healthy' : ($score >= 55 ? 'limited' : 'weak');
    }

    protected function confidenceWarnings(array $context): array
    {
        return array_values(array_intersect($context['reason_codes'], ['HIGH_UNCLASSIFIED_RATE', 'ATR_FAMILY_UNAVAILABLE', 'EXTREME_WINNER_DEPENDENCY']));
    }
}
