<?php

namespace App\Services\Sentiment;

class RuleBasedSentimentAnalyzer implements SentimentAnalyzerInterface
{
    /**
     * @var array<int, string>
     */
    protected array $positiveLexicon = [
        'naik', 'tumbuh', 'ekspansi', 'laba', 'untung', 'menguat', 'optimistis',
        'positif', 'rebound', 'solid', 'stabil', 'menggeliat', 'kuat', 'membaik', 'pulih',
        // Finance specific
        'dividen', 'oversubscribed', 'buyback', 'kontrak', 'laba', 'recovery',
    ];

    /**
     * @var array<int, string>
     */
    protected array $negativeLexicon = [
        'turun', 'rugi', 'melemah', 'penurunan', 'tekanan', 'anjlok', 'bearish',
        'negatif', 'terkoreksi', 'tertekan', 'downtrend', 'kontraksi',
        // Finance specific
        'gagal', 'default', 'suspensi', 'tekanan', 'margin',
    ];

    /**
     * @var array<int, string>
     */
    protected array $positivePhrases = [
        'laba tumbuh',
        'dividen',
        'ekspansi',
        'kontrak baru',
        'buyback',
        'oversubscribed',
        'kinerja solid',
    ];

    /**
     * @var array<int, string>
     */
    protected array $negativePhrases = [
        'rugi bersih',
        'gagal bayar',
        'tekanan margin',
        'penurunan pendapatan',
        'suspensi',
        'default',
    ];

    protected array $negations = ['tidak', 'bukan', 'belum'];

    public function analyze(string $text, array $context = []): array
    {
        $segments = $this->buildSegments($text, $context);

        $positiveScore = 0.0;
        $negativeScore = 0.0;
        $matchedPositive = [];
        $matchedNegative = [];
        $negationTriggered = false;

        foreach ($segments as $segment) {
            $lowerText = mb_strtolower($segment['text']);
            $tokens = $this->tokenize($segment['text']);

            // Phrase-level detection
            foreach ($this->positivePhrases as $phrase) {
                if (str_contains($lowerText, $phrase)) {
                    $positiveScore += 1.5 * $segment['weight'];
                    $matchedPositive[] = $phrase;
                }
            }
            foreach ($this->negativePhrases as $phrase) {
                if (str_contains($lowerText, $phrase)) {
                    $negativeScore += 1.5 * $segment['weight'];
                    $matchedNegative[] = $phrase;
                }
            }

            // Token-level detection + negation
            foreach ($tokens as $index => $token) {
                $weight = $segment['weight'];
                $next = $tokens[$index + 1] ?? null;

                // Negation handling
                if (in_array($token, $this->negations, true) && $next) {
                    if (in_array($next, $this->positiveLexicon, true)) {
                        $negativeScore += 1 * $weight;
                        $matchedNegative[] = "{$token} {$next}";
                        $negationTriggered = true;
                        continue;
                    }
                    if (in_array($next, $this->negativeLexicon, true)) {
                        $positiveScore += 1 * $weight;
                        $matchedPositive[] = "{$token} {$next}";
                        $negationTriggered = true;
                        continue;
                    }
                }

                if (in_array($token, $this->positiveLexicon, true)) {
                    $positiveScore += 1 * $weight;
                    $matchedPositive[] = $token;
                }

                if (in_array($token, $this->negativeLexicon, true)) {
                    $negativeScore += 1 * $weight;
                    $matchedNegative[] = $token;
                }
            }
        }

        $total = max($positiveScore + $negativeScore, 1);
        $score = ($positiveScore - $negativeScore) / $total;

        $label = $this->scoreToLabel($score);
        $confidence = $this->confidence($score, $positiveScore + $negativeScore);

        $reason = $this->buildReasonSummary($matchedPositive, $matchedNegative, $negationTriggered);

        return [
            'label' => $label,
            'score' => round($score, 2),
            'confidence' => $confidence,
            'method' => 'rule_based',
            'matched_positive_terms' => array_values(array_unique($matchedPositive)),
            'matched_negative_terms' => array_values(array_unique($matchedNegative)),
            'reason_summary' => $reason,
        ];
    }

    protected function buildSegments(string $fallbackText, array $context): array
    {
        $title = (string) ($context['title'] ?? '');
        $summary = (string) ($context['summary'] ?? '');
        $body = (string) ($context['body'] ?? $context['content'] ?? '');

        $segments = [
            ['text' => $title ?: $fallbackText, 'weight' => $title ? 1.5 : 1.0],
            ['text' => $summary ?: $fallbackText, 'weight' => $summary ? 1.0 : 0.9],
            ['text' => $body ?: $fallbackText, 'weight' => $body ? 0.8 : 0.8],
        ];

        return collect($segments)
            ->filter(fn ($seg) => trim($seg['text']) !== '')
            ->values()
            ->all();
    }

    protected function tokenize(string $text): array
    {
        $clean = mb_strtolower($text);
        $parts = preg_split('/[^a-zA-Z]+/u', $clean, -1, PREG_SPLIT_NO_EMPTY);

        return $parts ?: [];
    }

    protected function scoreToLabel(float $score): string
    {
        if ($score >= 0.15) {
            return 'positive';
        }

        if ($score <= -0.15) {
            return 'negative';
        }

        return 'neutral';
    }

    protected function confidence(float $score, float $signalStrength): float
    {
        $strengthFactor = min(1, $signalStrength / 6);
        $confidence = 0.4 + (abs($score) * 0.4) + ($strengthFactor * 0.2);

        return round(min(1, $confidence), 2);
    }

    protected function buildReasonSummary(array $positives, array $negatives, bool $negationTriggered): string
    {
        $posCount = count(array_unique($positives));
        $negCount = count(array_unique($negatives));

        $pieces = [];
        if ($posCount) {
            $pieces[] = "{$posCount} sinyal positif (".implode(', ', array_slice(array_unique($positives), 0, 3)).")";
        }
        if ($negCount) {
            $pieces[] = "{$negCount} sinyal negatif (".implode(', ', array_slice(array_unique($negatives), 0, 3)).")";
        }
        if ($negationTriggered) {
            $pieces[] = 'terdeteksi negasi (mis. "tidak/belum/bukan") yang membalik makna';
        }

        return $pieces ? implode('; ', $pieces) : 'Tidak ada sinyal kuat terdeteksi.';
    }
}
