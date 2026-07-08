<?php

namespace App\Services\Sentiment;

/**
 * Single source of truth for deciding the final sentiment_label when ML and rule-based
 * sentiment disagree. Manual validation of the full 801-article disagreement population
 * showed rule-based agrees with human judgement far more than ML (59.4% vs 35.6% -- ML is
 * worse than random guessing for a 3-class label). Every code path that persists
 * sentiment_label (news ingestion, analyze/reanalyze commands) MUST go through this
 * resolver instead of re-implementing the "always trust ML" default, or the fix silently
 * regresses the next time that path runs.
 */
class SentimentTiebreakResolver
{
    /**
     * @return array{label: ?string, score: ?float, confidence: ?float, method: ?string, agree: ?bool}
     */
    public static function resolve(
        ?string $mlLabel,
        ?string $ruleLabel,
        array $mlResult,
        array $ruleResult,
        string $mlMethod = 'python_unavailable'
    ): array {
        $agree = isset($mlLabel, $ruleLabel) ? $mlLabel === $ruleLabel : null;

        if ($agree === false && $ruleLabel !== null) {
            return [
                'label' => $ruleLabel,
                'score' => $ruleResult['score'] ?? $mlResult['score'] ?? null,
                'confidence' => $ruleResult['confidence'] ?? $mlResult['confidence'] ?? null,
                'method' => 'rule_based_tiebreak',
                'agree' => $agree,
            ];
        }

        return [
            'label' => $mlResult['label'] ?? $mlLabel,
            'score' => $mlResult['score'] ?? null,
            'confidence' => $mlResult['confidence'] ?? null,
            'method' => $mlResult['method'] ?? $mlMethod,
            'agree' => $agree,
        ];
    }
}
