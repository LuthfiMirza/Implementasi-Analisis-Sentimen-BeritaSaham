<?php

namespace App\Services\Prediction;

use App\Models\Stock;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Http;

/**
 * Builds the per-stock, per-model-variant prediction cards shown on the
 * Analytics & Prediksi page (technical/technical+sentiment for the 10
 * official tickers, or the BUMI/DEWA special models), backed by Python
 * when available and the baseline heuristic otherwise.
 */
class StockPredictionCardsService
{
    public function __construct(
        protected BaselinePredictionService $baselinePredictionService,
    ) {
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    public function buildPredictionsForStock(Stock $stock, array $features): array
    {
        return match ($stock->code) {
            'BUMI' => [
                'bumi_technical' => $this->predictVariant($features, 'bumi_technical'),
            ],
            'DEWA' => [
                'dewa_regime' => $this->predictVariant($features, 'dewa_regime'),
                'dewa_technical' => $this->predictVariant($features, 'dewa_technical'),
            ],
            default => $this->buildDualPredictions($features),
        };
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    protected function buildDualPredictions(array $features): array
    {
        return [
            'technical' => $this->predictVariant($features, 'technical'),
            'technical_sentiment' => $this->predictVariant($features, 'technical_sentiment'),
        ];
    }

    /**
     * @return array<string, mixed>
     */
    protected function predictVariant(array $features, string $variant): array
    {
        $pythonPrediction = $this->predictViaPython($features, $variant);
        if ($pythonPrediction !== null) {
            return $pythonPrediction;
        }

        return $this->normalizePrediction(
            $this->baselinePredictionService->predictFromFeatures($features),
            $variant,
            'fallback_heuristic'
        );
    }

    /**
     * Call the configured Python prediction endpoint and normalize its response.
     *
     * @return array<string, mixed>|null
     */
    protected function predictViaPython(array $features, string $variant): ?array
    {
        $endpoint = config('services.python_prediction.endpoint');
        if (! $endpoint) {
            return null;
        }

        try {
            $response = Http::timeout((int) config('services.python_prediction.timeout', 5))
                ->post($endpoint, ['features' => $features, 'model_variant' => $variant]);
            $payload = $response->successful() ? $response->json() : null;

            return is_array($payload) && (array_key_exists('predicted_direction', $payload) || array_key_exists('predicted_regime', $payload) || ($payload['has_sufficient_sentiment_data'] ?? null) === false)
                ? $this->normalizePrediction($payload, $variant, $this->modelSourceForVariant($variant))
                : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * Normalize prediction data into the page contract used by Blade and QA smoke tests.
     *
     * @return array<string, mixed>
     */
    protected function normalizePrediction(array $prediction, string $variant = 'technical', string $source = 'fallback_heuristic'): array
    {
        $hasDirection = filled($prediction['predicted_direction'] ?? null);

        return [
            'predicted_direction' => $hasDirection ? strtolower((string) $prediction['predicted_direction']) : null,
            'predicted_regime' => filled($prediction['predicted_regime'] ?? null) ? strtolower((string) $prediction['predicted_regime']) : null,
            'probability' => $prediction['probability'] ?? $prediction['confidence'] ?? null,
            'basis' => (string) ($prediction['basis'] ?? $prediction['prediction_basis'] ?? 'baseline_heuristic_v1'),
            'model_variant' => $prediction['model_variant'] ?? $variant,
            'model_source' => $prediction['model_source'] ?? $source,
            'model_name' => $prediction['model_name'] ?? ($source === 'fallback_heuristic' ? 'baseline_heuristic' : null),
            'model_version' => $prediction['model_version'] ?? null,
            'label_type' => $prediction['label_type'] ?? null,
            'has_sufficient_sentiment_data' => $prediction['has_sufficient_sentiment_data'] ?? null,
            'message' => $prediction['message'] ?? null,
            'scenario_bullish' => $prediction['scenario_bullish'] ?? null,
            'scenario_neutral' => $prediction['scenario_neutral'] ?? null,
            'scenario_bearish' => $prediction['scenario_bearish'] ?? null,
        ];
    }

    protected function modelSourceForVariant(string $variant): string
    {
        return match ($variant) {
            'technical' => 'v6a_technical',
            'technical_sentiment' => 'v6b_sentiment',
            'bumi_technical' => 'bumi_special',
            'dewa_regime' => 'dewa_regime',
            'dewa_technical' => 'dewa_special_directional',
            default => 'fallback_heuristic',
        };
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    public function latestRetrainStatus(): array
    {
        $path = storage_path('app/prediction/retrain_history.jsonl');
        if (! File::exists($path)) {
            return [];
        }

        return collect(explode("\n", trim((string) File::get($path))))
            ->filter()
            ->map(fn (string $line): mixed => json_decode($line, true))
            ->filter(fn (mixed $row): bool => is_array($row) && isset($row['model']))
            ->groupBy('model')
            ->map(fn ($rows): array => collect($rows)->last())
            ->all();
    }
}
