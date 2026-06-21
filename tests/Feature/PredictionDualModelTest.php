<?php

namespace Tests\Feature;

use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class PredictionDualModelTest extends TestCase
{
    public function test_prediction_page_calls_both_python_variants_and_renders_dual_cards(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 90);
        $this->seedArticle($stock);
        $this->configurePythonEndpoint();

        Http::fake(fn (Request $request) => Http::response(
            $this->pythonPayload($request->data()['model_variant'] ?? 'technical'),
            200
        ));

        $this->actingAsUser()
            ->get('/predictions?code=BBCA')
            ->assertOk()
            ->assertSee('Prediksi Teknikal', false)
            ->assertSee('Prediksi Teknikal + Sentimen', false)
            ->assertSee('v6a_technical', false)
            ->assertSee('v6b_sentiment', false)
            ->assertSee('decision support', false);

        Http::assertSent(fn (Request $request) => $request->data()['model_variant'] === 'technical');
        Http::assertSent(fn (Request $request) => $request->data()['model_variant'] === 'technical_sentiment');
    }

    public function test_prediction_page_renders_sentiment_unavailable_message(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 90);
        $this->seedArticle($stock);
        $this->configurePythonEndpoint();

        Http::fake(function (Request $request) {
            $variant = $request->data()['model_variant'] ?? 'technical';
            if ($variant === 'technical_sentiment') {
                return Http::response([
                    'predicted_direction' => null,
                    'probability' => null,
                    'model_variant' => 'technical_sentiment',
                    'has_sufficient_sentiment_data' => false,
                    'message' => 'Data sentimen berita untuk saham ini belum memadai pada periode ini, gunakan model Technical.',
                ], 200);
            }

            return Http::response($this->pythonPayload('technical'), 200);
        });

        $this->actingAsUser()
            ->get('/predictions?code=BBCA')
            ->assertOk()
            ->assertSee('Data sentimen belum memadai', false)
            ->assertSee('Data sentimen berita untuk saham ini belum memadai', false);
    }

    public function test_prediction_page_falls_back_to_heuristic_when_python_is_down(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 90);
        $this->seedArticle($stock);
        $this->configurePythonEndpoint();

        Http::fake(['python.test/predict' => Http::response(['detail' => 'down'], 503)]);

        $this->actingAsUser()
            ->get('/predictions?code=BBCA')
            ->assertOk()
            ->assertSee('fallback_heuristic', false)
            ->assertSee('Prediksi Teknikal', false)
            ->assertSee('Prediksi Teknikal + Sentimen', false);
    }

    public function test_api_predict_returns_dual_predictions_by_default(): void
    {
        $this->configurePythonEndpoint();
        Http::fake(fn (Request $request) => Http::response(
            $this->pythonPayload($request->data()['model_variant'] ?? 'technical'),
            200
        ));

        $response = $this->postJson('/api/predict', [
            'features' => $this->apiFeatures(),
        ]);

        $response->assertOk()
            ->assertJsonPath('predictions.technical.model_source', 'v6a_technical')
            ->assertJsonPath('predictions.technical_sentiment.model_source', 'v6b_sentiment')
            ->assertJsonPath('predictions.technical_sentiment.has_sufficient_sentiment_data', true)
            ->assertJsonPath('model_source', 'v6a_technical');
    }

    public function test_api_predict_can_return_specific_variant_and_fallback(): void
    {
        $this->configurePythonEndpoint();
        Http::fake(['python.test/predict' => Http::response(['detail' => 'down'], 503)]);

        $response = $this->postJson('/api/predict', [
            'model_variant' => 'technical_sentiment',
            'features' => $this->apiFeatures(),
        ]);

        $response->assertOk()
            ->assertJsonPath('model_variant', 'technical_sentiment')
            ->assertJsonPath('model_source', 'fallback_heuristic')
            ->assertJsonPath('model_name', 'baseline_heuristic');
    }

    private function configurePythonEndpoint(): void
    {
        Config::set('services.python_prediction.endpoint', 'https://python.test/predict');
        Config::set('services.python_prediction.timeout', 1);
    }

    /**
     * @return array<string, mixed>
     */
    private function pythonPayload(string $variant): array
    {
        return [
            'predicted_direction' => $variant === 'technical' ? 'up' : 'flat',
            'probability' => $variant === 'technical' ? 0.61 : 0.54,
            'basis' => 'Payload '.$variant,
            'model_variant' => $variant,
            'model_name' => $variant === 'technical' ? 'random_forest' : 'logistic_regression',
            'model_version' => $variant === 'technical' ? 'v6a_technical_random_forest_final' : 'v6b_technical_sentiment_logistic_regression_final',
            'has_sufficient_sentiment_data' => $variant === 'technical_sentiment' ? true : null,
            'scenario_bullish' => 'Bullish scenario',
            'scenario_neutral' => 'Neutral scenario',
            'scenario_bearish' => 'Bearish scenario',
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function apiFeatures(): array
    {
        return [
            'return_5d' => 0.01,
            'return_20d' => 0.02,
            'atr_ratio' => 0.03,
            'price_vs_ema20_pct' => 0.01,
            'regime_duration' => 5,
            'has_sentiment_data' => 1,
            'sentiment_average_5d' => 0.2,
            'weighted_sentiment_5d' => 0.25,
            'news_volume_5d' => 3,
            'sentiment_average_5d_x_regime' => 0.2,
            'weighted_sentiment_5d_x_regime' => 0.25,
        ];
    }
}
