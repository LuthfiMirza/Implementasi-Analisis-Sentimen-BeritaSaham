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
}
