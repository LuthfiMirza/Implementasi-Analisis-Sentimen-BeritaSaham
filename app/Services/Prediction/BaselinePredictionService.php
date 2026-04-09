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
            if (! isset($data['predicted_direction'])) {
                return null;
            }

            $confidence = isset($data['probability'])
                ? (float) $data['probability']
                : (isset($data['confidence']) ? (float) $data['confidence'] : 0.5);

            return [
                'predicted_direction' => strtolower((string) $data['predicted_direction']),
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
        $sentiment = (float) ($f['weighted_sentiment'] ?? $f['sentiment_average'] ?? 0);
        $maGap = (float) ($f['ma_gap'] ?? 0);
        $rsi = $f['rsi'] ?? null;
        $lag1 = $f['daily_return_lag1'] ?? 0;
        $lag3 = $f['daily_return_lag3'] ?? 0;

        $direction = 'flat';
        $confidence = 0.45;
        $basis = [];

        if ($sentiment > 0.2 && $maGap > 0 && $lag1 >= 0) {
            $direction = 'up';
            $confidence = 0.6 + min(0.2, ($sentiment / 2) + ($maGap * 2));
            $basis[] = 'Sentimen positif, harga di atas MA20, return pendek mendukung';
        } elseif ($sentiment < -0.2 && $maGap < 0 && $lag1 < 0) {
            $direction = 'down';
            $confidence = 0.6 + min(0.2, (abs($sentiment) / 2) + abs($maGap));
            $basis[] = 'Sentimen negatif, harga di bawah MA20, return melemah';
        } else {
            $direction = 'flat';
            $confidence = 0.45 + min(0.15, abs($sentiment) / 3);
            $basis[] = 'Sinyal campuran, kecenderungan netral';
        }

        if ($rsi !== null) {
            if ($direction === 'up' && $rsi >= 60) {
                $confidence += 0.05;
                $basis[] = 'RSI mendukung momentum naik';
            } elseif ($direction === 'down' && $rsi <= 40) {
                $confidence += 0.05;
                $basis[] = 'RSI lemah mendukung tekanan turun';
            } elseif ($rsi >= 70) {
                $basis[] = 'RSI tinggi, waspadai jenuh beli';
            }
        }

        if ($lag3 !== null && $direction === 'flat') {
            if ($lag3 > 0.5 && $sentiment > 0) {
                $direction = 'up';
                $basis[] = 'Return 3 hari positif dan sentimen ikut naik';
            } elseif ($lag3 < -0.5 && $sentiment < 0) {
                $direction = 'down';
                $basis[] = 'Return 3 hari negatif sejalan sentimen';
            }
        }

        $probability = round(min(0.95, max(0.35, $confidence)), 2);

        return [
            'predicted_direction' => $direction,
            'confidence' => $probability,
            'method' => 'baseline',
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
}
