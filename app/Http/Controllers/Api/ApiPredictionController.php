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
        ]);

        if ($validator->fails()) {
            return response()->json([
                'error' => 'Missing required features',
                'required' => self::REQUIRED_FEATURES,
            ], 422);
        }

        $features = $validator->validated()['features'];
        if (config('prediction.engine', env('PREDICTION_ENGINE', 'baseline')) === 'python') {
            $python = $this->postJson(
                (string) config('services.python_prediction.endpoint'),
                (int) config('services.python_prediction.timeout', 5),
                ['features' => $features],
            );
            if (is_array($python) && isset($python['predicted_direction'])) {
                return response()->json($python);
            }
        }

        return response()->json($this->normalizePrediction($baselinePredictionService->predictFromFeatures($features)));
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
    protected function normalizePrediction(array $prediction): array
    {
        return [
            'predicted_direction' => strtolower((string) ($prediction['predicted_direction'] ?? 'flat')),
            'probability' => (float) ($prediction['probability'] ?? $prediction['confidence'] ?? 0.45),
            'basis' => (string) ($prediction['basis'] ?? $prediction['prediction_basis'] ?? 'baseline_heuristic_v1'),
            'scenario_bullish' => (string) ($prediction['scenario_bullish'] ?? ''),
            'scenario_neutral' => (string) ($prediction['scenario_neutral'] ?? ''),
            'scenario_bearish' => (string) ($prediction['scenario_bearish'] ?? ''),
        ];
    }
}
