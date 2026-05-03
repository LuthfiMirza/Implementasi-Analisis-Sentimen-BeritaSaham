<?php

namespace Tests\Feature;

use App\Services\Prediction\BaselinePredictionService;
use App\Services\Prediction\ResearchPredictionFeatureService;
use App\Services\Prediction\ResearchRankingService;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class PythonApiIntegrationTest extends TestCase
{
    public function test_python_predict_with_valid_features_returns_direction_probability_and_basis(): void
    {
        Config::set('prediction.engine', 'python');
        Config::set('prediction.python_endpoint', 'https://python.test/predict');
        Http::fake(['python.test/predict' => Http::response([
            'predicted_direction' => 'up',
            'probability' => 0.77,
            'basis' => 'model test',
        ])]);

        $result = (new BaselinePredictionService())->predict(['return_5d' => 0.03]);

        // Laravel integration should preserve the FastAPI prediction contract.
        $this->assertSame('up', $result['predicted_direction']);
        $this->assertSame(0.77, $result['confidence']);
        $this->assertSame('model test', $result['prediction_basis']);
    }

    public function test_python_predict_with_missing_feature_keys_is_validation_gap(): void
    {
        Config::set('prediction.engine', 'python');
        Config::set('prediction.python_endpoint', 'https://python.test/predict');
        Http::fake(['python.test/predict' => Http::response(['detail' => 'missing feature'], 422)]);

        $result = (new BaselinePredictionService())->predict([]);

        // Current Laravel integration falls back to baseline; QA flags this as not exposing FastAPI 422.
        $this->assertSame('baseline_fallback', $result['method']);
    }

    public function test_python_rank_stocks_valid_payload_returns_ranked_array_metadata(): void
    {
        Config::set('prediction.ranking_endpoint', 'https://python.test/rank-stocks');
        $this->seedStock('BBCA');
        $this->seedStock('BBRI');
        Http::fake(['python.test/rank-stocks' => Http::response([
            'ranked' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.8, 'signal' => 'candidate'],
                ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.4, 'signal' => 'neutral'],
            ],
            'model_version' => 'test-v1',
            'horizon_days' => 5,
        ])]);

        $result = (new ResearchRankingService($this->featureService()))->getRanking(['BBCA', 'BBRI']);

        // Ranking responses need metadata for paper-trading traceability.
        $this->assertTrue($result['available']);
        $this->assertCount(2, $result['ranked']);
        $this->assertSame('test-v1', $result['model_version']);
        $this->assertSame(5, $result['horizon_days']);
    }

    public function test_python_rank_stocks_empty_stocks_array_returns_empty_without_crash(): void
    {
        $result = (new ResearchRankingService($this->featureService()))->getRanking([]);

        // Empty watchlists should produce a controlled unavailable response.
        $this->assertFalse($result['available']);
        $this->assertSame([], $result['ranked']);
    }

    private function featureService(): ResearchPredictionFeatureService
    {
        return new class extends ResearchPredictionFeatureService {
            public function seriesForStock(\App\Models\Stock $stock): Collection
            {
                return collect(['2026-04-30' => ['return_5d' => 0.02]]);
            }
            public function buildForDate(\App\Models\Stock $stock, Collection $articles, $referenceDate, int $sentimentLookbackDays = 5): array
            {
                return ['return_5d' => 0.02, 'reference_date' => '2026-04-30'];
            }
        };
    }
}
