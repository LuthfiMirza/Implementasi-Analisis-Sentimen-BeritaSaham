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
        $predictionSource = 'baseline';

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

            if (config('prediction.engine', env('PREDICTION_ENGINE', 'baseline')) === 'python') {
                $pythonPrediction = $this->predictViaPython($features);
                if ($pythonPrediction !== null) {
                    $prediction = $pythonPrediction;
                    $predictionSource = 'python_api';
                } else {
                    $predictionSource = 'baseline_fallback';
                }
            }

            $prediction ??= $this->normalizePrediction($baselinePredictionService->predictFromFeatures($features));
        }

        return view('predictions.index', compact('stock', 'prediction', 'predictionSource', 'stocks'));
    }

    /**
     * Call the configured Python prediction endpoint and normalize its response.
     *
     * @return array<string, mixed>|null
     */
    protected function predictViaPython(array $features): ?array
    {
        $endpoint = config('services.python_prediction.endpoint');
        if (! $endpoint) {
            return null;
        }

        try {
            $response = Http::timeout((int) config('services.python_prediction.timeout', 5))
                ->post($endpoint, ['features' => $features]);
            $payload = $response->successful() ? $response->json() : null;

            return is_array($payload) && isset($payload['predicted_direction'])
                ? $this->normalizePrediction($payload)
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
    protected function normalizePrediction(array $prediction): array
    {
        return [
            'predicted_direction' => strtolower((string) ($prediction['predicted_direction'] ?? 'flat')),
            'probability' => (float) ($prediction['probability'] ?? $prediction['confidence'] ?? 0.45),
            'basis' => (string) ($prediction['basis'] ?? $prediction['prediction_basis'] ?? 'baseline_heuristic_v1'),
            'scenario_bullish' => $prediction['scenario_bullish'] ?? null,
            'scenario_neutral' => $prediction['scenario_neutral'] ?? null,
            'scenario_bearish' => $prediction['scenario_bearish'] ?? null,
        ];
    }
}
