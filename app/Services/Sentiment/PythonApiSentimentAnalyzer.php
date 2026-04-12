<?php

namespace App\Services\Sentiment;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
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
        $endpoint = config('sentiment.python_endpoint', env('PYTHON_SENTIMENT_ENDPOINT'));
        $token = config('sentiment.huggingface_token', env('HUGGINGFACE_API_TOKEN'));
        $timeout = (int) config('sentiment.python_timeout', env('PYTHON_SENTIMENT_TIMEOUT', 15));

        if (! $endpoint) {
            return $this->fallback->analyze($text, $context);
        }

        $inputText = trim(implode('. ', array_filter([
            $context['title'] ?? null,
            $context['summary'] ?? null,
            $text,
        ])));
        $inputText = mb_substr($inputText, 0, 512);

        try {
            $headers = ['Accept' => 'application/json'];
            if ($token) {
                $headers['Authorization'] = 'Bearer '.$token;
            }

            $response = Http::withHeaders($headers)
                ->timeout($timeout)
                ->post($endpoint, ['inputs' => $inputText]);

            if (! $response->successful()) {
                Log::warning('HuggingFace sentiment failed', [
                    'status' => $response->status(),
                    'body' => substr($response->body(), 0, 200),
                ]);

                return $this->fallback->analyze($text, $context);
            }

            $data = $response->json();
            $predictions = $data[0] ?? $data ?? [];

            if (empty($predictions)) {
                return $this->fallback->analyze($text, $context);
            }

            $best = collect($predictions)->sortByDesc('score')->first();
            $label = Str::lower($best['label'] ?? 'neutral');
            $confidence = round((float) ($best['score'] ?? 0.5), 4);

            $label = match ($label) {
                'positive', 'pos', 'label_2' => 'positive',
                'negative', 'neg', 'label_0' => 'negative',
                default => 'neutral',
            };

            $score = match ($label) {
                'positive' => round($confidence, 2),
                'negative' => round(-$confidence, 2),
                default => 0.0,
            };

            $ruleResult = $this->fallback->analyze($text, $context);

            return [
                'label' => $label,
                'score' => $this->normalizeScore($score),
                'confidence' => $confidence !== null ? min(1, max(0, round($confidence, 2))) : null,
                'method' => 'python',
                'matched_positive_terms' => $ruleResult['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $ruleResult['matched_negative_terms'] ?? [],
                'reason_summary' => 'IndoBERT: '.$label.' ('.round($confidence * 100, 1).'%) | Rule: '.($ruleResult['label'] ?? 'neutral'),
                'ml_label' => $label,
                'ml_confidence' => $confidence,
                'ml_score' => $score,
                'rule_label' => $ruleResult['label'] ?? 'neutral',
                'rule_score' => $ruleResult['score'] ?? 0,
            ];
        } catch (\Throwable $e) {
            Log::warning('HuggingFace sentiment exception', ['error' => $e->getMessage()]);
        }

        return $this->fallback->analyze($text, $context);
    }

    protected function normalizeScore(float $score): float
    {
        return max(-1.0, min(1.0, round($score, 2)));
    }

    protected function isValidPayload(?array $data): bool
    {
        if (! is_array($data)) {
            return false;
        }

        if (! isset($data['label'])) {
            return false;
        }

        $label = Str::lower((string) $data['label']);
        $allowed = ['positive', 'neutral', 'negative'];

        return in_array($label, $allowed, true);
    }
}
