<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\Prediction\BaselinePredictionService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Validator;

class ApiPredictionController extends Controller
{
    protected const REQUIRED_FEATURES = [
        'return_5d',
        'return_20d',
        'atr_ratio',
        'price_vs_ema20_pct',
        'regime_duration',
    ];

    /**
     * Proxy `/api/predict` to Python when configured, otherwise return a baseline prediction.
     */
    public function predict(Request $request, BaselinePredictionService $baselinePredictionService): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'features' => ['required', 'array'],
            'features.return_5d' => ['required', 'numeric'],
            'features.return_20d' => ['required', 'numeric'],
            'features.atr_ratio' => ['required', 'numeric'],
            'features.price_vs_ema20_pct' => ['required', 'numeric'],
            'features.regime_duration' => ['required', 'integer'],
            'model_variant' => ['nullable', 'in:technical,technical_sentiment'],
        ]);

        if ($validator->fails()) {
            return response()->json([
                'error' => 'Missing required features',
                'required' => self::REQUIRED_FEATURES,
            ], 422);
        }

        $features = $request->input('features', []);
        $requestedVariant = $validator->validated()['model_variant'] ?? null;

        if ($requestedVariant) {
            return response()->json($this->predictVariant($features, $baselinePredictionService, $requestedVariant));
        }

        $predictions = [
            'technical' => $this->predictVariant($features, $baselinePredictionService, 'technical'),
            'technical_sentiment' => $this->predictVariant($features, $baselinePredictionService, 'technical_sentiment'),
        ];

        return response()->json(array_merge($predictions['technical'], [
            'predictions' => $predictions,
        ]));
    }

    /**
     * @return array<string, mixed>
     */
    protected function predictVariant(array $features, BaselinePredictionService $baselinePredictionService, string $variant): array
    {
        $python = $this->postJson(
            (string) config('services.python_prediction.endpoint'),
            (int) config('services.python_prediction.timeout', 5),
            ['features' => $features, 'model_variant' => $variant],
        );

        if (is_array($python) && (array_key_exists('predicted_direction', $python) || ($python['has_sufficient_sentiment_data'] ?? null) === false)) {
            return $this->normalizePrediction($python, $variant, $variant === 'technical' ? 'v6a_technical' : 'v6b_sentiment');
        }

        return $this->normalizePrediction(
            $baselinePredictionService->predictFromFeatures($features),
            $variant,
            'fallback_heuristic'
        );
    }

    /**
     * Proxy `/api/rank-stocks` to the ranking service without inventing fallback rankings.
     */
    public function rankStocks(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'stocks' => ['required', 'array'],
            'stocks.*.ticker' => ['required', 'string'],
            'stocks.*.features' => ['required', 'array'],
        ]);

        if (count($validated['stocks']) === 0) {
            return response()->json([
                'ranked' => [],
                'model_version' => 'v5_ranking',
                'horizon_days' => 5,
                'generated_at' => now()->toDateString(),
            ]);
        }

        $endpoint = (string) config('services.python_ranking.endpoint');
        if ($endpoint !== '') {
            $python = $this->postJson(
                $endpoint,
                (int) config('services.python_ranking.timeout', 5),
                $request->all(),
            );
            if (is_array($python) && isset($python['ranked']) && is_array($python['ranked'])) {
                return response()->json($python);
            }
        }

        return response()->json([
            'ranked' => [],
            'model_version' => 'unavailable',
            'horizon_days' => 5,
            'generated_at' => now()->toDateString(),
            'error' => 'Ranking service unavailable',
        ]);
    }

    /**
     * Send an HTTP JSON request using Laravel's faked Http client.
     *
     * @return array<string, mixed>|null
     */
    protected function postJson(string $endpoint, int $timeout, array $payload): ?array
    {
        if ($endpoint === '') {
            return null;
        }

        try {
            $response = Http::timeout($timeout)->post($endpoint, $payload);

            return $response->successful() && is_array($response->json()) ? $response->json() : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * Normalize baseline service output into the public API response contract.
     *
     * @return array<string, mixed>
     */
    protected function normalizePrediction(array $prediction, string $variant = 'technical', string $source = 'fallback_heuristic'): array
    {
        $hasDirection = filled($prediction['predicted_direction'] ?? null);

        return [
            'predicted_direction' => $hasDirection ? strtolower((string) $prediction['predicted_direction']) : null,
            'probability' => $prediction['probability'] ?? $prediction['confidence'] ?? null,
            'basis' => (string) ($prediction['basis'] ?? $prediction['prediction_basis'] ?? 'baseline_heuristic_v1'),
            'model_variant' => $prediction['model_variant'] ?? $variant,
            'model_source' => $prediction['model_source'] ?? $source,
            'model_name' => $prediction['model_name'] ?? ($source === 'fallback_heuristic' ? 'baseline_heuristic' : null),
            'model_version' => $prediction['model_version'] ?? null,
            'has_sufficient_sentiment_data' => $prediction['has_sufficient_sentiment_data'] ?? null,
            'message' => $prediction['message'] ?? null,
            'scenario_bullish' => (string) ($prediction['scenario_bullish'] ?? ''),
            'scenario_neutral' => (string) ($prediction['scenario_neutral'] ?? ''),
            'scenario_bearish' => (string) ($prediction['scenario_bearish'] ?? ''),
        ];
    }
}
