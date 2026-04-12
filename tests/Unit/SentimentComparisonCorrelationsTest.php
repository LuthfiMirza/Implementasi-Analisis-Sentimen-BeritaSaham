<?php

namespace Tests\Unit;

use App\Services\Analytics\SentimentComparisonService;
use Illuminate\Support\Collection;
use Tests\TestCase;

class SentimentComparisonCorrelationsTest extends TestCase
{
    public function test_same_day_and_lag_correlations_are_computed(): void
    {
        $service = $this->app->make(SentimentComparisonService::class);

        $perDate = collect([
            '2024-01-01' => ['avg' => 0.2, 'weighted_avg' => 0.3, 'count' => 2],
            '2024-01-02' => ['avg' => -0.1, 'weighted_avg' => -0.15, 'count' => 1],
            '2024-01-03' => ['avg' => 0.05, 'weighted_avg' => 0.08, 'count' => 1],
        ]);

        $returns = [
            '2024-01-01' => 0.01,
            '2024-01-02' => -0.02,
            '2024-01-03' => 0.03,
            '2024-01-04' => 0.01,
            '2024-01-06' => -0.01,
        ];

        $ref = new \ReflectionClass($service);
        $method = $ref->getMethod('compareCorrelations');
        $method->setAccessible(true);
        $result = $method->invoke($service, $perDate, $returns);

        $this->assertArrayHasKey('same_day', $result);
        $this->assertArrayHasKey('lag', $result);
        $this->assertArrayHasKey('average', $result['same_day']);
        $this->assertArrayHasKey('weighted', $result['lag']['h1']);
    }
}
