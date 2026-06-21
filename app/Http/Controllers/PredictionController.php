<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use App\Services\Prediction\BaselinePredictionService;
use App\Services\Prediction\FeatureBuilderService;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\View\View;

class PredictionController extends Controller
{
    /**
     * Display a stock prediction page backed by Python when available and baseline otherwise.
     */
    public function index(
        Request $request,
        PriceSeriesService $priceSeriesService,
        SentimentPriceAnalyticsService $analyticsService,
        FeatureBuilderService $featureBuilderService,
        BaselinePredictionService $baselinePredictionService
    ): View {
        $stocks = Stock::query()
            ->where('is_active', true)
            ->orderBy('code')
            ->get();
        $defaultCode = $stocks->first()?->code ?? 'BBCA';
        $code = strtoupper((string) $request->query('code', $defaultCode));
        $stock = Stock::query()
            ->where('code', $code)
            ->first() ?? $stocks->first();

        $prediction = null;
        $predictionSource = 'fallback_heuristic';
        $predictions = [];

        if ($stock) {
            $prices = $priceSeriesService->getSeries($stock, '1d', 90)->values();
            $articles = NewsArticle::query()
                ->forStockContext($stock)
                ->whereNotNull('published_at')
                ->latest('published_at')
                ->limit(50)
                ->get();
            $analytics = $analyticsService->analyze($stock, $prices, $articles, 30);
            $features = $featureBuilderService->build($stock, $prices, $articles, $analytics, 30);

            $predictions = $this->buildPredictionsForStock($stock, $features, $baselinePredictionService);
            $prediction = $predictions['technical']
                ?? $predictions['bumi_technical']
                ?? $predictions['dewa_technical']
                ?? $predictions['dewa_regime']
                ?? null;
            $predictionSource = $prediction['model_source'] ?? 'fallback_heuristic';
        }

        return view('predictions.index', compact('stock', 'prediction', 'predictionSource', 'predictions', 'stocks'));
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    protected function buildPredictionsForStock(Stock $stock, array $features, BaselinePredictionService $baselinePredictionService): array
    {
        return match ($stock->code) {
            'BUMI' => [
                'bumi_technical' => $this->predictVariant($features, $baselinePredictionService, 'bumi_technical'),
            ],
            'DEWA' => [
                'dewa_regime' => $this->predictVariant($features, $baselinePredictionService, 'dewa_regime'),
                'dewa_technical' => $this->predictVariant($features, $baselinePredictionService, 'dewa_technical'),
            ],
            default => $this->buildDualPredictions($features, $baselinePredictionService),
        };
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    protected function buildDualPredictions(array $features, BaselinePredictionService $baselinePredictionService): array
    {
        return [
            'technical' => $this->predictVariant($features, $baselinePredictionService, 'technical'),
            'technical_sentiment' => $this->predictVariant($features, $baselinePredictionService, 'technical_sentiment'),
        ];
    }

    /**
     * @return array<string, mixed>
     */
    protected function predictVariant(array $features, BaselinePredictionService $baselinePredictionService, string $variant): array
    {
        $pythonPrediction = $this->predictViaPython($features, $variant);
        if ($pythonPrediction !== null) {
            return $pythonPrediction;
        }

        return $this->normalizePrediction(
            $baselinePredictionService->predictFromFeatures($features),
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
}
