<?php

namespace App\Services\News;

use App\Models\NewsArticle;
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
        $result = $analyzer->analyze(
            $article->summary ?? $article->content_snippet ?? $article->title,
            [
                'title' => $article->title,
                'summary' => $article->summary,
                'body' => $article->full_text ?? $article->content_snippet,
                'language' => $article->language ?? 'id',
            ]
        );

        $article->forceFill([
            'sentiment_label' => $result['label'],
            'sentiment_score' => $result['score'],
            'sentiment_confidence' => $result['confidence'] ?? null,
            'sentiment_method' => $result['method'] ?? 'python_unavailable',
            'sentiment_meta' => [
                'matched_positive_terms' => $result['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $result['matched_negative_terms'] ?? [],
                'reason_summary' => $result['reason_summary'] ?? null,
                'python_status' => $result['python_status'] ?? null,
            ],
            'analyzed_at' => now(),
        ])->save();
    }
}
