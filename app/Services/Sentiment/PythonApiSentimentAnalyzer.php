<?php

namespace App\Services\Sentiment;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class PythonApiSentimentAnalyzer implements SentimentAnalyzerInterface
{
    public function __construct(
        protected ?SentimentAnalyzerInterface $legacyFallback = null
    ) {
    }

    public function analyze(string $text, array $context = []): array
    {
        $endpoint = config('sentiment.python_endpoint', env('PYTHON_SENTIMENT_ENDPOINT'));
        $token = config('sentiment.huggingface_token', env('HUGGINGFACE_API_TOKEN'));
        $timeout = (int) config('sentiment.python_timeout', env('PYTHON_SENTIMENT_TIMEOUT', 15));

        if (! $endpoint) {
            return $this->unavailableResult('python_endpoint_missing', 'Python sentiment endpoint is not configured.');
        }

        $inputText = trim(implode('. ', array_filter([
            $context['title'] ?? null,
            $context['summary'] ?? null,
            strlen($text) < 200 ? $text : null,
        ])));
        if ($inputText === '') {
            $inputText = $text;
        }
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
                Log::warning('Python sentiment request failed', [
                    'status' => $response->status(),
                    'stock' => $context['stock_code'] ?? null,
                ]);

                return $this->unavailableResult(
                    'python_http_error',
                    sprintf('Python sentiment endpoint returned HTTP %d.', $response->status())
                );
            }

            $data = $response->json();
            $parsed = is_array($data) ? $this->parseResponse($data) : null;
            if (! $parsed) {
                Log::warning('Python sentiment payload invalid', [
                    'stock' => $context['stock_code'] ?? null,
                    'payload_type' => get_debug_type($data),
                ]);

                return $this->unavailableResult('python_invalid_payload', 'Python sentiment payload was invalid.');
            }

            return [
                'label' => $parsed['label'],
                'score' => $parsed['score'],
                'confidence' => $parsed['confidence'],
                'method' => 'python',
                'python_status' => 'available',
                'ml_label' => $parsed['label'],
                'ml_confidence' => $parsed['confidence'],
                'ml_score' => $parsed['score'],
                'rule_label' => null,
                'rule_score' => null,
                'ml_prob_positive' => (float) ($parsed['prob_positive'] ?? 0),
                'ml_prob_neutral' => (float) ($parsed['prob_neutral'] ?? 0),
                'ml_prob_negative' => (float) ($parsed['prob_negative'] ?? 0),
                'matched_positive_terms' => $parsed['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $parsed['matched_negative_terms'] ?? [],
                'reason_summary' => sprintf(
                    'IndoBERT: %s (%.1f%% confidence)',
                    $parsed['label'],
                    $parsed['confidence'] * 100
                ),
            ];
        } catch (\Throwable $e) {
            Log::warning('Python sentiment exception', ['error' => $e->getMessage()]);

            return $this->unavailableResult('python_exception', 'Python sentiment request raised an exception.');
        }
    }

    protected function parseResponse(array $data): ?array
    {
        if (isset($data['label'])) {
            $label = $this->normalizeLabel((string) ($data['label'] ?? 'neutral'));
            $confidence = round((float) ($data['confidence'] ?? abs((float) ($data['score'] ?? 0.5))), 4);
            $score = isset($data['score'])
                ? round((float) $data['score'], 2)
                : match ($label) {
                    'positive' => round($confidence, 2),
                    'negative' => round(-$confidence, 2),
                    default => 0.0,
                };

            return [
                'label' => $label,
                'score' => $score,
                'confidence' => $confidence,
                'prob_positive' => $label === 'positive' ? $confidence : 0.0,
                'prob_neutral' => $label === 'neutral' ? $confidence : 0.0,
                'prob_negative' => $label === 'negative' ? $confidence : 0.0,
                'matched_positive_terms' => $data['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $data['matched_negative_terms'] ?? [],
            ];
        }

        $predictions = $data[0] ?? null;
        if (! is_array($predictions) || $predictions === []) {
            return null;
        }

        $scores = collect($predictions)->keyBy(fn ($prediction) => strtolower((string) ($prediction['label'] ?? '')));
        $best = collect($predictions)->sortByDesc('score')->first();
        if (! is_array($best)) {
            return null;
        }

        $label = $this->normalizeLabel((string) ($best['label'] ?? 'neutral'));
        $confidence = round((float) ($best['score'] ?? 0.5), 4);
        $score = match ($label) {
            'positive' => round($confidence, 2),
            'negative' => round(-$confidence, 2),
            default => 0.0,
        };

        return [
            'label' => $label,
            'score' => $score,
            'confidence' => $confidence,
            'prob_positive' => (float) ($scores['positive']['score'] ?? 0),
            'prob_neutral' => (float) ($scores['neutral']['score'] ?? 0),
            'prob_negative' => (float) ($scores['negative']['score'] ?? 0),
        ];
    }

    protected function normalizeLabel(string $label): string
    {
        return match (strtolower($label)) {
            'positive', 'pos' => 'positive',
            'negative', 'neg' => 'negative',
            default => 'neutral',
        };
    }

    protected function unavailableResult(string $status, string $reason): array
    {
        return [
            'label' => 'neutral',
            'score' => 0.0,
            'confidence' => 0.0,
            'method' => 'python_unavailable',
            'python_status' => $status,
            'ml_label' => null,
            'ml_confidence' => null,
            'ml_score' => null,
            'rule_label' => null,
            'rule_score' => null,
            'ml_prob_positive' => null,
            'ml_prob_neutral' => null,
            'ml_prob_negative' => null,
            'matched_positive_terms' => [],
            'matched_negative_terms' => [],
            'reason_summary' => $reason,
        ];
    }
}
