<?php

namespace App\Services\News;

use App\Models\NewsArticle;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use App\Services\Sentiment\SentimentEngineManager;

class SentimentAnalysisService
{
    public function __construct(
        protected ?SentimentEngineManager $engineManager = null
    ) {
        $this->engineManager ??= new SentimentEngineManager();
    }

    public function analyzeAndUpdate(NewsArticle $article): void
    {
        $analyzer = $this->engineManager->getAnalyzer();
        $baselineAnalyzer = new RuleBasedSentimentAnalyzer();
        $result = $analyzer->analyze(
            $article->summary ?? $article->content_snippet ?? $article->title,
            [
                'title' => $article->title,
                'summary' => $article->summary,
                'body' => $article->full_text ?? $article->content_snippet,
                'language' => $article->language ?? 'id',
            ]
        );
        $baseline = $baselineAnalyzer->analyze(
            $article->summary ?? $article->content_snippet ?? $article->title,
            [
                'title' => $article->title,
                'summary' => $article->summary,
                'body' => $article->full_text ?? $article->content_snippet,
                'language' => $article->language ?? 'id',
                'stock_code' => $article->stock?->code,
            ]
        );

        $mlLabel = $result['ml_label'] ?? $article->ml_sentiment_label;
        $ruleLabel = $result['rule_label'] ?? $baseline['label'] ?? $article->rule_sentiment_label;
        $agree = isset($mlLabel, $ruleLabel) ? $mlLabel === $ruleLabel : $article->ml_rule_agree;

        // Manual validation (801 human-labeled articles, the full ml_rule_agree=false population)
        // showed rule-based agrees with human judgement far more than ML when the two disagree
        // (59.4% vs 35.6%) — ML in particular over-calls positive/negative when the true tone is
        // neutral. Prefer the rule-based label as final when they disagree instead of always
        // trusting ML.
        if ($agree === false && $ruleLabel !== null) {
            $finalLabel = $ruleLabel;
            $finalScore = $baseline['score'] ?? $result['score'];
            $finalConfidence = $baseline['confidence'] ?? $result['confidence'] ?? null;
            $finalMethod = 'rule_based_tiebreak';
        } else {
            $finalLabel = $result['label'];
            $finalScore = $result['score'];
            $finalConfidence = $result['confidence'] ?? null;
            $finalMethod = $result['method'] ?? 'python_unavailable';
        }

        $article->forceFill([
            'sentiment_label' => $finalLabel,
            'sentiment_score' => $finalScore,
            'sentiment_confidence' => $finalConfidence,
            'sentiment_method' => $finalMethod,
            'sentiment_meta' => [
                'matched_positive_terms' => $result['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $result['matched_negative_terms'] ?? [],
                'reason_summary' => $result['reason_summary'] ?? null,
                'python_status' => $result['python_status'] ?? null,
            ],
            'ml_sentiment_label' => $mlLabel,
            'ml_sentiment_score' => $result['ml_score'] ?? $article->ml_sentiment_score,
            'ml_confidence' => $result['ml_confidence'] ?? $article->ml_confidence,
            'ml_prob_positive' => $result['ml_prob_positive'] ?? $article->ml_prob_positive,
            'ml_prob_neutral' => $result['ml_prob_neutral'] ?? $article->ml_prob_neutral,
            'ml_prob_negative' => $result['ml_prob_negative'] ?? $article->ml_prob_negative,
            'rule_sentiment_label' => $ruleLabel,
            'rule_sentiment_score' => $result['rule_score'] ?? $baseline['score'] ?? $article->rule_sentiment_score,
            'ml_rule_agree' => $agree,
            'analyzed_at' => now(),
        ])->save();
    }
}
