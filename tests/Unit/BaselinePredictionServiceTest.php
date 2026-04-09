<?php

namespace Tests\Unit;

use App\Services\Prediction\BaselinePredictionService;
use Tests\TestCase;

class BaselinePredictionServiceTest extends TestCase
{
    public function test_baseline_prediction_uptrend(): void
    {
        $service = new BaselinePredictionService(null, 3);
        $features = [
            'sentiment_average' => 0.3,
            'weighted_sentiment' => 0.35,
            'ma_gap' => 0.05,
            'daily_return_lag1' => 1.2,
            'daily_return_lag3' => 2.5,
            'rsi' => 62,
        ];

        $result = $service->predict($features);

        $this->assertSame('up', $result['predicted_direction']);
        $this->assertGreaterThan(0.5, $result['confidence']);
    }

    public function test_baseline_prediction_downtrend(): void
    {
        $service = new BaselinePredictionService(null, 3);
        $features = [
            'sentiment_average' => -0.35,
            'weighted_sentiment' => -0.4,
            'ma_gap' => -0.04,
            'daily_return_lag1' => -1.5,
            'daily_return_lag3' => -2.1,
            'rsi' => 38,
        ];

        $result = $service->predict($features);

        $this->assertSame('down', $result['predicted_direction']);
    }
}
