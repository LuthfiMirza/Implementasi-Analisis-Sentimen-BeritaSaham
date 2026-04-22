<?php

namespace App\Services\Sentiment;

class SentimentEngineManager
{
    public function getAnalyzer(): SentimentAnalyzerInterface
    {
        $engine = function_exists('config') ? config('sentiment.engine', env('SENTIMENT_ENGINE', 'python')) : env('SENTIMENT_ENGINE', 'python');

        return match ($engine) {
            'rule_based' => new RuleBasedSentimentAnalyzer(),
            'hybrid' => new HybridSentimentAnalyzer(
                new PythonApiSentimentAnalyzer(),
                new RuleBasedSentimentAnalyzer()
            ),
            default => new PythonApiSentimentAnalyzer(),
        };
    }
}
