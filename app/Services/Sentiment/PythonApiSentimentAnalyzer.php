<?php

namespace App\Services\Sentiment;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class PythonApiSentimentAnalyzer implements SentimentAnalyzerInterface
{
    public function __construct(
        protected ?SentimentAnalyzerInterface $fallback = null
    ) {
        $this->fallback ??= new RuleBasedSentimentAnalyzer();
    }

    public function analyze(string $text, array $context = []): array
    {
        $endpoint = function_exists('config') ? config('sentiment.python_endpoint', env('PYTHON_SENTIMENT_ENDPOINT')) : env('PYTHON_SENTIMENT_ENDPOINT');
        $timeout = (int) (function_exists('config') ? config('sentiment.python_timeout', env('PYTHON_SENTIMENT_TIMEOUT', 5)) : env('PYTHON_SENTIMENT_TIMEOUT', 5));

        if (! $endpoint) {
            return $this->fallback->analyze($text, $context);
        }

        try {
            $payload = [
                'text' => $text,
                'context' => [
                    'title' => $context['title'] ?? null,
                    'summary' => $context['summary'] ?? null,
                    'body' => $context['body'] ?? $context['content'] ?? null,
                ],
                'language' => $context['language'] ?? 'id',
            ];
            $response = Http::timeout($timeout)->post($endpoint, $payload);

            if ($response->successful()) {
                $data = $response->json();
                $fallback = $this->fallback->analyze($text, $context);

                if (isset($data['label'])) {
                    $score = isset($data['score']) ? (float) $data['score'] : ($fallback['score'] ?? 0.0);
                    $confidence = isset($data['confidence']) ? (float) $data['confidence'] : ($fallback['confidence'] ?? null);

                    return [
                        'label' => Str::lower((string) $data['label']),
                        'score' => $this->normalizeScore($score),
                        'confidence' => $confidence !== null ? min(1, max(0, round($confidence, 2))) : null,
                        'method' => 'python',
                        'matched_positive_terms' => $data['matched_positive_terms'] ?? $fallback['matched_positive_terms'] ?? [],
                        'matched_negative_terms' => $data['matched_negative_terms'] ?? $fallback['matched_negative_terms'] ?? [],
                        'reason_summary' => $data['reason_summary'] ?? $fallback['reason_summary'] ?? null,
                    ];
                }
            }
        } catch (\Throwable $e) {
            // Silent fallback to rule-based when API is unreachable
        }

        return $this->fallback->analyze($text, $context);
    }

    protected function normalizeScore(float $score): float
    {
        return max(-1.0, min(1.0, round($score, 2)));
    }
}
