<?php

namespace App\Services\Sentiment;

class HybridSentimentAnalyzer implements SentimentAnalyzerInterface
{
    public function __construct(
        protected ?PythonApiSentimentAnalyzer $pythonAnalyzer = null,
        protected ?RuleBasedSentimentAnalyzer $ruleBasedAnalyzer = null
    ) {
        $this->ruleBasedAnalyzer ??= new RuleBasedSentimentAnalyzer();
        $this->pythonAnalyzer ??= new PythonApiSentimentAnalyzer();
    }

    public function analyze(string $text, array $context = []): array
    {
        $engine = function_exists('config') ? config('sentiment.engine', env('SENTIMENT_ENGINE', 'python')) : env('SENTIMENT_ENGINE', 'python');
        if ($engine === 'rule_based') {
            $result = $this->ruleBasedAnalyzer->analyze($text, $context);
            $result['method'] = $result['method'] ?? 'rule_based';
            $result['confidence'] = $result['confidence'] ?? $this->defaultConfidence($result['score'] ?? 0.0);

            return $result;
        }

        $result = $this->pythonAnalyzer->analyze($text, $context);
        $result['confidence'] = $result['confidence'] ?? $this->defaultConfidence($result['score'] ?? 0.0);

        return $result;
    }

    protected function defaultConfidence(float $score): float
    {
        return round(min(1, 0.5 + abs($score) * 0.4), 2);
    }
}
