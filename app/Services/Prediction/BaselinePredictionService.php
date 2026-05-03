<?php

namespace App\Services\Prediction;

use Illuminate\Support\Facades\Http;

class BaselinePredictionService
{
    public function __construct(
        protected ?string $pythonEndpoint = null,
        protected int $timeout = 6,
    ) {
        $this->pythonEndpoint ??= $this->cfg('prediction.python_endpoint', env('PYTHON_PREDICTION_ENDPOINT'));
        $this->timeout = (int) $this->cfg('prediction.timeout', env('PYTHON_PREDICTION_TIMEOUT', 6));
    }

    public function predict(array $features): array
    {
        $engine = $this->cfg('prediction.engine', env('PREDICTION_ENGINE', 'baseline'));

        if ($engine === 'python') {
            $pythonResult = $this->predictViaPython($features);
            if ($pythonResult) {
                return $pythonResult;
            }
            // fallback baseline jika python gagal
            $result = $this->baselineHeuristic($features);
            $result['method'] = 'baseline_fallback';
            return $result;
        }

        // default / engine lain fallback baseline
        return $this->baselineHeuristic($features);
    }

    /**
     * Produce a compact baseline prediction from normalized technical features.
     *
     * @return array<string, mixed>
     */
    public function predictFromFeatures(array $features): array
    {
        $return5d = (float) ($features['return_5d'] ?? 0);
        $priceVsEma20 = (float) ($features['price_vs_ema20_pct'] ?? $features['price_vs_ema20'] ?? 0);

        if ($return5d > 0.01 && $priceVsEma20 > 0) {
            $direction = 'up';
            $probability = 0.62;
        } elseif ($return5d < -0.01 && $priceVsEma20 < 0) {
            $direction = 'down';
            $probability = 0.58;
        } else {
            $direction = 'flat';
            $probability = 0.45;
        }

        return [
            'predicted_direction' => $direction,
            'probability' => $probability,
            'basis' => 'baseline_heuristic_v1',
            'scenario_bullish' => 'Momentum harga jangka pendek bertahan di atas tren EMA20.',
            'scenario_neutral' => 'Sinyal teknikal belum cukup kuat untuk arah naik atau turun.',
            'scenario_bearish' => 'Momentum harga melemah dan posisi relatif terhadap EMA20 negatif.',
        ];
    }

    protected function predictViaPython(array $features): ?array
    {
        if (! $this->pythonEndpoint) {
            return null;
        }

        try {
            $response = Http::timeout($this->timeout)->post($this->pythonEndpoint, ['features' => $features]);
            if (! $response->successful()) {
                return null;
            }

            $data = $response->json();
            if (! $this->isValidPrediction($data)) {
                return null;
            }

            $confidence = isset($data['probability'])
                ? (float) $data['probability']
                : (isset($data['confidence']) ? (float) $data['confidence'] : 0.5);
            $direction = strtolower((string) $data['predicted_direction']);

            return [
                'predicted_direction' => $direction,
                'confidence' => round(min(0.99, max(0.01, $confidence)), 2),
                'method' => 'python',
                'prediction_basis' => $data['basis'] ?? 'Prediksi dari model Python eksternal.',
                'scenario_bullish' => $data['scenario_bullish'] ?? 'Jika sentimen dan harga selaras naik, potensi kenaikan berlanjut.',
                'scenario_neutral' => $data['scenario_neutral'] ?? 'Jika sinyal bercampur, pergerakan cenderung datar.',
                'scenario_bearish' => $data['scenario_bearish'] ?? 'Jika sentimen memburuk dan harga gagal di atas MA, risiko turun meningkat.',
            ];
        } catch (\Throwable $e) {
            return null;
        }
    }

    protected function baselineHeuristic(array $f): array
    {
        $sentiment = (float) ($f['weighted_sentiment_quality'] ?? $f['weighted_sentiment'] ?? $f['sentiment_average'] ?? 0);
        $maGap = (float) ($f['ma_gap'] ?? 0);
        $rsi = $f['rsi'] ?? null;
        $lag1 = (float) ($f['daily_return_lag1'] ?? 0);
        $lag3 = (float) ($f['daily_return_lag3'] ?? 0);
        $lag7 = (float) ($f['daily_return_lag7'] ?? 0);
        $volatility = (float) ($f['volatility'] ?? 0);
        $newsVolume = (int) ($f['news_volume'] ?? 0);
        $positiveNews = (int) ($f['positive_news_count'] ?? 0);
        $negativeNews = (int) ($f['negative_news_count'] ?? 0);
        $neutralNews = (int) ($f['neutral_news_count'] ?? 0);
        $cumulativeReturn = $f['cumulative_return'] ?? null;
        $priceTrend = strtolower((string) ($f['price_trend'] ?? 'datar'));
        $correlationH1 = $f['lag_correlation_h1'] ?? null;
        $correlationH3 = $f['lag_correlation_h3'] ?? null;
        $macroAttention = (float) ($f['macro_regulatory_attention_score'] ?? 0.0);
        $macroCaution = (bool) ($f['macro_regulatory_caution_flag'] ?? false);
        $macroConfidenceMultiplier = (float) ($f['macro_regulatory_confidence_multiplier'] ?? 1.0);
        $macroScoreMultiplier = (float) ($f['macro_regulatory_score_multiplier'] ?? 1.0);
        $macroThresholdTightening = (float) ($f['macro_regulatory_threshold_tightening_factor'] ?? 1.0);
        $macroRegime = (string) ($f['macro_regulatory_attention_regime'] ?? 'normal');

        $sentimentSignal = $this->clamp($sentiment / 0.35);
        $maSignal = $this->clamp($maGap / 0.025);
        $lag1Signal = $this->clamp($lag1 / 1.8);
        $lag3Signal = $this->clamp($lag3 / 3.8);
        $lag7Signal = $this->clamp($lag7 / 6.0);
        $rsiSignal = $rsi !== null ? $this->clamp(((float) $rsi - 50) / 18) : 0.0;
        $cumSignal = $cumulativeReturn !== null ? $this->clamp(((float) $cumulativeReturn) / 8) : 0.0;
        $newsBalance = ($positiveNews + $negativeNews) > 0
            ? $this->clamp(($positiveNews - $negativeNews) / max(1, $positiveNews + $negativeNews))
            : 0.0;
        $coverageFactor = $newsVolume > 0 ? min(1.0, $newsVolume / 8) : 0.0;
        $trendSignal = match ($priceTrend) {
            'naik' => 0.7,
            'turun' => -0.7,
            default => 0.0,
        };
        $corrSignal = $this->clamp((((float) ($correlationH1 ?? 0)) * 0.6) + (((float) ($correlationH3 ?? 0)) * 0.4), -0.6, 0.6);

        $sentimentWeight = $coverageFactor >= 0.5 ? 0.24 : 0.10;
        $newsFlowWeight = $coverageFactor >= 0.5 ? 0.12 : 0.04;

        $directionalEdge =
            ($sentimentSignal * $sentimentWeight) +
            ($newsBalance * $newsFlowWeight) +
            ($maSignal * 0.18) +
            ($lag1Signal * 0.14) +
            ($lag3Signal * 0.20) +
            ($lag7Signal * 0.10) +
            ($rsiSignal * 0.10) +
            ($cumSignal * 0.06) +
            ($trendSignal * 0.10) +
            ($corrSignal * 0.06);

        if ($macroCaution) {
            $directionalEdge *= max(0.0, min(1.0, $macroScoreMultiplier));
        }

        $componentSigns = collect([
            $sentimentSignal,
            $newsBalance,
            $maSignal,
            $lag1Signal,
            $lag3Signal,
            $lag7Signal,
            $rsiSignal,
            $trendSignal,
        ])->filter(fn ($value) => abs($value) >= 0.15)->values();

        $positiveComponents = $componentSigns->filter(fn ($value) => $value > 0)->count();
        $negativeComponents = $componentSigns->filter(fn ($value) => $value < 0)->count();
        $consensus = $componentSigns->count() > 0
            ? abs($positiveComponents - $negativeComponents) / $componentSigns->count()
            : 0.0;

        $volatilityPenalty = $volatility > 2.5 ? min(0.12, ($volatility - 2.5) / 15) : 0.0;
        $neutralityBoost = $neutralNews > ($positiveNews + $negativeNews) ? 0.04 : 0.0;
        $macroPenalty = $macroCaution ? min(0.10, $macroAttention * 0.12) : 0.0;
        $conviction = max(0.0, abs($directionalEdge) - $volatilityPenalty - $neutralityBoost - $macroPenalty);

        $upScore = $this->scorePercent(0.5 + max(0, $directionalEdge));
        $downScore = $this->scorePercent(0.5 + max(0, -$directionalEdge));
        $flatScore = $this->scorePercent(1 - min(0.9, $conviction + (abs($directionalEdge) * 0.5)));

        $direction = 'flat';
        $directionThreshold = 0.16 * max(1.0, $macroThresholdTightening);
        if ($directionalEdge >= $directionThreshold && $conviction >= 0.12) {
            $direction = 'up';
        } elseif ($directionalEdge <= (-1 * $directionThreshold) && $conviction >= 0.12) {
            $direction = 'down';
        }

        $confidence = 0.42
            + min(0.28, $conviction * 0.65)
            + min(0.10, $consensus * 0.10)
            + min(0.08, $coverageFactor * 0.08)
            - min(0.06, $volatilityPenalty * 0.5);
        if ($macroCaution) {
            $confidence *= max(0.0, min(1.0, $macroConfidenceMultiplier));
        }

        $basis = [];
        if ($coverageFactor > 0) {
            $basis[] = sprintf(
                'Sentimen %s (%.2f) dengan coverage %d berita',
                $sentiment > 0 ? 'positif' : ($sentiment < 0 ? 'negatif' : 'netral'),
                $sentiment,
                $newsVolume
            );
        } else {
            $basis[] = 'Coverage berita tipis, model lebih mengandalkan price action';
        }

        if ($maSignal > 0.15) {
            $basis[] = 'MA5 berada di atas MA20';
        } elseif ($maSignal < -0.15) {
            $basis[] = 'MA5 berada di bawah MA20';
        }

        if ($lag3Signal > 0.2 || $lag7Signal > 0.2) {
            $basis[] = 'Momentum 3-7 hari mendukung kenaikan';
        } elseif ($lag3Signal < -0.2 || $lag7Signal < -0.2) {
            $basis[] = 'Momentum 3-7 hari mendukung pelemahan';
        }

        if ($rsi !== null) {
            if ($rsi >= 60) {
                $basis[] = 'RSI mendukung momentum bullish';
            } elseif ($rsi <= 40) {
                $basis[] = 'RSI mendukung tekanan bearish';
            }
        }

        if ($direction === 'flat') {
            $basis[] = 'Skor bullish dan bearish masih berdekatan';
        }
        if ($macroCaution) {
            $basis[] = 'Regulatory '.$macroRegime.' OJK menurunkan conviction directional dan confidence';
        }

        $probability = round(min(0.95, max(0.35, $confidence)), 2);

        return [
            'predicted_direction' => $direction,
            'confidence' => $probability,
            'method' => 'baseline_score',
            'scores' => [
                'up' => $upScore,
                'flat' => $flatScore,
                'down' => $downScore,
                'edge' => round($directionalEdge, 4),
                'conviction' => round($conviction, 4),
                'consensus' => round($consensus, 4),
            ],
            'prediction_basis' => implode('; ', $basis),
            'scenario_bullish' => 'Jika sentimen tetap positif dan harga bertahan di atas MA20, kecenderungan bullish berlanjut.',
            'scenario_neutral' => 'Jika sinyal bercampur, harga cenderung bergerak datar sambil menunggu katalis.',
            'scenario_bearish' => 'Jika sentimen kembali negatif dan harga gagal di atas MA20, risiko pelemahan lebih besar.',
        ];
    }

    protected function cfg(string $key, $default = null)
    {
        return function_exists('config') ? config($key, $default) : $default;
    }

    protected function isValidPrediction(?array $data): bool
    {
        if (! is_array($data)) {
            return false;
        }

        if (! isset($data['predicted_direction'])) {
            return false;
        }

        $direction = strtolower((string) $data['predicted_direction']);

        return in_array($direction, ['up', 'down', 'flat'], true);
    }

    protected function clamp(float $value, float $min = -1.0, float $max = 1.0): float
    {
        return max($min, min($max, $value));
    }

    protected function scorePercent(float $value): float
    {
        return round(max(0, min(100, $value * 100)), 1);
    }
}
