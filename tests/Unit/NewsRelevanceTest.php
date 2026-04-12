<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\RelevanceScoringService;
use App\Services\News\StockKeywordMapper;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NewsRelevanceTest extends TestCase
{
    use RefreshDatabase;

    public function test_noise_article_for_ambiguous_ticker_is_low_quality(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'GOTO',
            'company_name' => 'GoTo Gojek Tokopedia',
        ]);

        $service = new RelevanceScoringService(new StockKeywordMapper());
        $result = $service->score($stock, [
            'title' => 'Let us go to the park this weekend',
            'summary' => 'Random travel article unrelated to market',
            'language' => 'en',
        ], 'newsapi');

        $this->assertLessThan(0.3, $result['final_quality_score']);
        $this->assertEquals('low', $result['quality_band']);
    }

    public function test_market_context_article_scores_high(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia Tbk',
        ]);

        $service = new RelevanceScoringService(new StockKeywordMapper());
        $result = $service->score($stock, [
            'title' => 'BBCA catat kenaikan laba dan rencana bagi dividen saham',
            'summary' => 'Laporan kinerja kuartal dengan konteks IHSG dan investor',
            'language' => 'id',
        ], 'newsapi');

        $this->assertGreaterThan(0.6, $result['final_quality_score']);
        $this->assertEquals('high', $result['quality_band']);
    }
}
