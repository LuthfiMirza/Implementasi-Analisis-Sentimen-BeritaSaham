<?php

namespace Tests\Unit;

use App\Services\Analytics\DecisionSupportService;
use Tests\TestCase;

class DecisionSupportServiceTest extends TestCase
{
    public function test_decision_support_returns_status_confidence_and_factor_arrays(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 45);
        $this->seedArticle($stock);

        $result = (new DecisionSupportService())->analyze($stock, $stock->prices, $stock->newsArticles);

        // DSS labels are user-facing thesis recommendations.
        $this->assertContains($result['status'], ['Bullish Support', 'Wait and See', 'Warning']);
        $this->assertContains($result['confidence'], ['Rendah', 'Sedang', 'Tinggi']);
        $this->assertIsArray($result['supporting_factors']);
        $this->assertIsArray($result['weakening_factors']);
        $this->assertIsArray($result['risk_factors']);
        $this->assertNotEmpty($result['supporting_factors'] + $result['weakening_factors'] + $result['risk_factors']);
    }

    public function test_decision_support_with_no_news_data_does_not_crash(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 45);

        $result = (new DecisionSupportService())->analyze($stock, $stock->prices, collect());

        // No-news periods should degrade to neutral decision support, not fatal errors.
        $this->assertContains($result['status'], ['Bullish Support', 'Wait and See', 'Warning']);
        $this->assertContains($result['confidence'], ['Rendah', 'Sedang', 'Tinggi']);
    }

    /**
     * Audit 2026-07-19 (output/prediction_research/dss_scoring_weights_audit.txt) found the
     * composite score has no reliable relationship with subsequent returns. Status now derives
     * from the validated prediction model instead -- these tests lock that behavior in place.
     */
    public function test_status_is_bullish_support_when_prediction_direction_is_up(): void
    {
        $this->bindFakePrediction(['predicted_direction' => 'up', 'confidence' => 0.5]);
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 45);
        $this->seedArticle($stock);

        $result = (new DecisionSupportService())->analyze($stock, $stock->prices, $stock->newsArticles);

        $this->assertSame('Bullish Support', $result['status']);
        $this->assertSame('Tinggi', $result['confidence']);
    }

    public function test_status_is_warning_when_prediction_direction_is_down(): void
    {
        $this->bindFakePrediction(['predicted_direction' => 'down', 'confidence' => 0.4]);
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 45);
        $this->seedArticle($stock);

        $result = (new DecisionSupportService())->analyze($stock, $stock->prices, $stock->newsArticles);

        $this->assertSame('Warning', $result['status']);
        $this->assertSame('Sedang', $result['confidence']);
    }

    public function test_status_is_wait_and_see_when_prediction_direction_is_flat(): void
    {
        $this->bindFakePrediction(['predicted_direction' => 'flat', 'confidence' => 0.34]);
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 45);
        $this->seedArticle($stock);

        $result = (new DecisionSupportService())->analyze($stock, $stock->prices, $stock->newsArticles);

        $this->assertSame('Wait and See', $result['status']);
        $this->assertSame('Rendah', $result['confidence']);
    }

    protected function bindFakePrediction(array $prediction): void
    {
        $this->app->bind(\App\Services\Prediction\BaselinePredictionService::class, function () use ($prediction) {
            return new class($prediction) extends \App\Services\Prediction\BaselinePredictionService {
                public function __construct(private array $fakePrediction)
                {
                }

                public function predict(array $features): array
                {
                    return $this->fakePrediction;
                }
            };
        });
    }
}
