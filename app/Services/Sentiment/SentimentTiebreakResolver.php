<?php

namespace App\Services\Sentiment;

/**
 * Single source of truth for deciding the final sentiment_label when ML and rule-based
 * sentiment disagree. ML now runs a fine-tuned IndoBERT model (trained 2026-07-19 on 801
 * manually labeled disagreement cases, served locally via quant/sentiment_api.py) instead
 * of the raw pretrained checkpoint used when this resolver was first written. Re-measured
 * on a held-out test split, restricted to exactly the condition this resolver acts on
 * (fine-tuned ML disagrees with rule-based): ML matches human judgement 55.8% of the time
 * vs rule-based only 32.7% -- the original 2026-07-07 finding (rule-based 59.4% vs raw ML
 * 35.6%) is now inverted because ML improved, not because rule-based got worse. Every code
 * path that persists sentiment_label (news ingestion, analyze/reanalyze commands) MUST go
 * through this resolver instead of re-implementing an "always trust X" default, or the
 * policy silently regresses the next time that path runs.
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

        if ($agree === false && $mlLabel !== null) {
            return [
                'label' => $mlResult['label'] ?? $mlLabel,
                'score' => $mlResult['score'] ?? $ruleResult['score'] ?? null,
                'confidence' => $mlResult['confidence'] ?? $ruleResult['confidence'] ?? null,
                'method' => 'ml_tiebreak',
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
