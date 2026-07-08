<?php

namespace App\Services\News;

use App\Models\NewsArticle;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use App\Services\Sentiment\SentimentEngineManager;
use App\Services\Sentiment\SentimentTiebreakResolver;

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

        $resolved = SentimentTiebreakResolver::resolve($mlLabel, $ruleLabel, $result, $baseline);

        $article->forceFill([
            'sentiment_label' => $resolved['label'],
            'sentiment_score' => $resolved['score'],
            'sentiment_confidence' => $resolved['confidence'],
            'sentiment_method' => $resolved['method'],
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
            'ml_rule_agree' => $resolved['agree'] ?? $article->ml_rule_agree,
            'analyzed_at' => now(),
        ])->save();
    }
}
