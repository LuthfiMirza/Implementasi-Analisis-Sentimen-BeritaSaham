<?php

namespace App\Services\Sentiment;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

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
        $token    = config('sentiment.huggingface_token', env('HUGGINGFACE_API_TOKEN'));
        $timeout  = (int) config('sentiment.python_timeout', env('PYTHON_SENTIMENT_TIMEOUT', 15));

        if (! $endpoint) {
            return $this->fallback->analyze($text, $context);
        }

        // Build rich input: title + summary (max 512 chars for IndoBERT)
        $inputText = trim(implode('. ', array_filter([
            $context['title']   ?? null,
            $context['summary'] ?? null,
            strlen($text) < 200 ? $text : null,
        ])));
        if (empty($inputText)) {
            $inputText = $text;
        }
        $inputText = mb_substr($inputText, 0, 512);

        try {
            $headers = ['Accept' => 'application/json'];
            if ($token) {
                $headers['Authorization'] = 'Bearer ' . $token;
            }

            $response = Http::withHeaders($headers)
                ->timeout($timeout)
                ->post($endpoint, ['inputs' => $inputText]);

            if (! $response->successful()) {
                Log::warning('HuggingFace sentiment failed', [
                    'status' => $response->status(),
                    'stock'  => $context['stock_code'] ?? null,
                ]);
                return $this->fallback->analyze($text, $context);
            }

            $data = $response->json();

            [$parsed, $ruleResult] = $this->parseResponse($data, $text, $context);
            if (! $parsed) {
                return $this->fallback->analyze($text, $context);
            }

            return [
                'label'      => $parsed['label'],
                'score'      => $parsed['score'],
                'confidence' => $parsed['confidence'],
                'method'     => 'python',

                // For comparison storage
                'ml_label'      => $parsed['label'],
                'ml_confidence' => $parsed['confidence'],
                'ml_score'      => $parsed['score'],
                'rule_label'    => $ruleResult['label']  ?? 'neutral',
                'rule_score'    => $ruleResult['score']  ?? 0.0,

                // All 3 class probabilities (useful for evaluation)
                'ml_prob_positive' => (float) ($parsed['prob_positive'] ?? 0),
                'ml_prob_neutral'  => (float) ($parsed['prob_neutral'] ?? 0),
                'ml_prob_negative' => (float) ($parsed['prob_negative'] ?? 0),

                'matched_positive_terms' => $parsed['matched_positive_terms'] ?? ($ruleResult['matched_positive_terms'] ?? []),
                'matched_negative_terms' => $parsed['matched_negative_terms'] ?? ($ruleResult['matched_negative_terms'] ?? []),
                'reason_summary' => sprintf(
                    'IndoBERT: %s (%.1f%%) | Rule: %s',
                    $parsed['label'],
                    $parsed['confidence'] * 100,
                    $ruleResult['label'] ?? 'neutral'
                ),
            ];
        } catch (\Throwable $e) {
            Log::warning('HuggingFace exception', ['error' => $e->getMessage()]);
            return $this->fallback->analyze($text, $context);
        }
    }

    protected function parseResponse(array $data, string $text, array $context): array
    {
        if (isset($data['label'])) {
            $label = $this->normalizeLabel($data['label'] ?? 'neutral');
            $confidence = round((float) ($data['confidence'] ?? abs((float) ($data['score'] ?? 0.5))), 4);
            $score = isset($data['score'])
                ? round((float) $data['score'], 2)
                : match ($label) {
                    'positive' => round($confidence, 2),
                    'negative' => round(-$confidence, 2),
                    default => 0.0,
                };

            return [[
                'label' => $label,
                'score' => $score,
                'confidence' => $confidence,
                'prob_positive' => $label === 'positive' ? $confidence : 0.0,
                'prob_neutral' => $label === 'neutral' ? $confidence : 0.0,
                'prob_negative' => $label === 'negative' ? $confidence : 0.0,
                'matched_positive_terms' => $data['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $data['matched_negative_terms'] ?? [],
            ], $this->fallback->analyze($text, $context)];
        }

        $predictions = $data[0] ?? [];
        if (empty($predictions)) {
            return [null, $this->fallback->analyze($text, $context)];
        }

        $scores = collect($predictions)->keyBy(fn ($p) => strtolower($p['label']));
        $best   = collect($predictions)->sortByDesc('score')->first();

        $label = $this->normalizeLabel($best['label'] ?? 'neutral');
        $confidence = round((float) ($best['score'] ?? 0.5), 4);
        $score = match ($label) {
            'positive' => round($confidence, 2),
            'negative' => round(-$confidence, 2),
            default => 0.0,
        };

        return [[
            'label' => $label,
            'score' => $score,
            'confidence' => $confidence,
            'prob_positive' => (float) ($scores['positive']['score'] ?? 0),
            'prob_neutral' => (float) ($scores['neutral']['score'] ?? 0),
            'prob_negative' => (float) ($scores['negative']['score'] ?? 0),
        ], $this->fallback->analyze($text, $context)];
    }

    protected function normalizeLabel(string $label): string
    {
        return match (strtolower($label)) {
            'positive', 'pos' => 'positive',
            'negative', 'neg' => 'negative',
            default => 'neutral',
        };
    }
}
