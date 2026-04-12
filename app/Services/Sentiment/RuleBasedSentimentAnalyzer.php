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
        // Pergerakan harga positif
        'melesat', 'terbang', 'melonjak', 'rebound', 'rally', 'all time high', 'ath', 'bullish', 'hijau', 'lompat', 'meroket',
        // Kinerja keuangan positif
        'profit', 'pertumbuhan', 'tumbuh', 'rekor', 'tertinggi', 'surplus', 'optimis',
        // Aksi korporasi positif
        'ekspansi', 'akuisisi', 'merger', 'rights issue', 'ipo', 'listing', 'upgrade',
        // Rating/rek hit
        'overweight', 'outperform', 'buy', 'strong buy',
        'dividen jumbo', 'laba bersih', 'laba naik', 'pendapatan naik', 'aset naik',
        'npf turun', 'npl turun', 'car naik', 'saham bonus', 'akuisisi strategis',
        'kinerja positif', 'melampaui ekspektasi', 'beat ekspektasi',
        'pemangkasan suku bunga', 'bi rate turun', 'suku bunga turun',
        'capital inflow', 'net buy', 'beli bersih', 'foreign buy',
        'rekor tertinggi', 'level tertinggi', 'capai rekor',
        'ihsg melesat', 'ihsg naik', 'ihsg menguat', 'ihsg hijau', 'ihsg lompat', 'ihsg terbang', 'pasar modal menguat',
    ];

    /**
     * @var array<int, string>
     */
    protected array $negativeLexicon = [
        'turun', 'rugi', 'melemah', 'penurunan', 'tekanan', 'anjlok', 'bearish',
        'negatif', 'terkoreksi', 'tertekan', 'downtrend', 'kontraksi',
        // Finance specific
        'gagal', 'default', 'suspensi', 'tekanan', 'margin',
        // Pergerakan harga negatif
        'jatuh', 'terpuruk', 'ambruk', 'longsor', 'merah', 'koreksi', 'all time low', 'atl', 'tertekan',
        // Risiko
        'risiko tinggi', 'krisis', 'gagal bayar', 'delisting', 'sanksi ojk', 'denda ojk',
        // Makro negatif
        'inflasi tinggi', 'resesi', 'pelemahan rupiah',
        'melemah', 'bearish', 'tekanan jual', 'profit taking', 'aksi jual',
        'defisit', 'kerugian bersih', 'rugi bersih', 'pendapatan turun', 'laba turun', 'laba merosot',
        'npl naik', 'kredit macet', 'pembekuan', 'sanksi ojk', 'denda ojk',
        'underweight', 'underperform', 'sell', 'strong sell',
        'stagflasi', 'rupiah melemah', 'capital outflow', 'net sell', 'jual bersih', 'foreign sell',
        'ihsg anjlok', 'ihsg turun', 'ihsg melemah', 'ihsg merah', 'pasar saham turun', 'bursa melemah',
        'krisis likuiditas',
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
        'all time high',
        'hak memesan efek terlebih dahulu',
        'overweight',
        'outperform',
        'strong buy',
        'laba bersih naik',
        'pendapatan naik',
        'bi rate turun',
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
        'all time low',
        'ancaman delisting',
        'underweight',
        'underperform',
        'strong sell',
        'laba turun',
        'pendapatan turun',
        'pelemahan rupiah',
        'net sell',
    ];

    protected array $neutralPatterns = [
        'jadwal', 'operasional', 'libur lebaran', 'libur nasional',
        'agenda', 'rapat umum', 'rups',
    ];

    protected array $strongPositivePhrases = [
        'buyback saham', 'bagi dividen', 'tebar dividen', 'dividen jumbo',
        'laba bersih naik', 'ihsg melesat', 'ihsg lompat', 'ihsg menguat',
        'ihsg terbang', 'ihsg happy', 'saham naik', 'menguat signifikan',
        'rekor tertinggi', 'net buy asing', 'foreign net buy', 'bi rate turun',
        'simak jadwal buyback', 'jadwal buyback', 'saham bonus',
        'dividen rp', 'tebar dividen', 'sepakat bagi dividen',
        'laba rp', 'catat laba', 'raup laba', 'cetak laba',
        'melesat', 'lompat', 'terbang', 'melonjak',
    ];

    protected array $strongNegativePhrases = [
        'ihsg anjlok', 'ihsg turun', 'ihsg melemah', 'saham anjlok',
        'gagal bayar', 'kredit macet', 'net sell asing', 'asing jual',
        'laba turun', 'rugi bersih', 'delisting paksa',
        'jatuh ke bawah', 'pangsa pasar jatuh', 'volume menyusut',
        'di bawah 50', 'ambruk', 'longsor', 'terpuruk',
    ];

    protected array $negations = ['tidak', 'bukan', 'belum'];

    public function analyze(string $text, array $context = []): array
    {
        $segments = $this->buildSegments($text, $context);

        $positiveScore = 0.0;
        $negativeScore = 0.0;
        $strongScore = 0.0;
        $matchedPositive = [];
        $matchedNegative = [];
        $negationTriggered = false;

        foreach ($segments as $segment) {
            $lowerText = mb_strtolower($segment['text']);
            $tokens = $this->tokenize($segment['text']);
            $neutralHit = false;

            // Strong phrase detection (override tendency)
            foreach ($this->strongNegativePhrases as $phrase) {
                if (str_contains($lowerText, $phrase)) {
                    $strongScore -= 2.0 * $segment['weight'];
                    $matchedNegative[] = $phrase;
                }
            }
            foreach ($this->strongPositivePhrases as $phrase) {
                if (str_contains($lowerText, $phrase)) {
                    $strongScore += 2.0 * $segment['weight'];
                    $matchedPositive[] = $phrase;
                }
            }

            foreach ($this->neutralPatterns as $neutral) {
                if (str_contains($lowerText, $neutral)) {
                    $neutralHit = true;
                }
            }

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

            // If segment only matched neutral patterns and no pos/neg yet, keep neutral
            if ($neutralHit && $positiveScore === 0.0 && $negativeScore === 0.0) {
                continue;
            }
        }

        $rawScore = $strongScore + ($positiveScore - $negativeScore);
        $signalStrength = max(abs($strongScore) + $positiveScore + $negativeScore, 1);
        $score = max(-1, min(1, $rawScore / $signalStrength));

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
        if ($score >= 0.10) {
            return 'positive';
        }

        if ($score <= -0.10) {
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
