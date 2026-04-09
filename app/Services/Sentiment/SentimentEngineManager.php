<?php

namespace App\Services\Sentiment;

class SentimentEngineManager
{
    public function getAnalyzer(): SentimentAnalyzerInterface
    {
        $engine = function_exists('config') ? config('sentiment.engine', env('SENTIMENT_ENGINE', 'hybrid')) : env('SENTIMENT_ENGINE', 'hybrid');

        return match ($engine) {
            'rule_based' => new RuleBasedSentimentAnalyzer(),
            'python' => new PythonApiSentimentAnalyzer(new RuleBasedSentimentAnalyzer()),
            default => new HybridSentimentAnalyzer(
                new PythonApiSentimentAnalyzer(new RuleBasedSentimentAnalyzer()),
                new RuleBasedSentimentAnalyzer()
            ),
        };
    }
}
