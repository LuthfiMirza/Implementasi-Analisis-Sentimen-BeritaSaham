<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\Prediction\ResearchPredictionFeatureService;
use Illuminate\Support\Collection;
use Tests\TestCase;

class ResearchPredictionFeatureServiceTest extends TestCase
{
    public function test_prediction_label_threshold_matches_v6a_fixed_one_point_five_percent(): void
    {
        $service = new class extends ResearchPredictionFeatureService {
            public function seriesForStock(Stock $stock): Collection
            {
                return collect([
                    '2026-04-30' => [
                        'return_1d' => 0.01,
                        'return_3d' => 0.02,
                        'return_5d' => 0.03,
                        'return_20d' => 0.04,
                    ],
                ]);
            }
        };

        $features = $service->buildForDate(
            new Stock(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']),
            collect(),
            '2026-04-30'
        );

        $this->assertSame(0.015, $features['prediction_label_threshold']);
    }
}
