<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\RelevanceScoringService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RelevanceScoringServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_high_relevance_when_title_matches(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Bank Central Asia umumkan dividen',
            'summary' => 'BBCA bagikan dividen besar',
            'source_url' => 'https://example.com/a',
        ], 'newsapi');

        $this->assertEquals('high', $result['relevance_band']);
        $this->assertGreaterThan(0.6, $result['relevance_score']);
    }

    public function test_low_relevance_when_no_match(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Cuaca cerah di Jakarta',
            'summary' => 'Prakiraan cuaca',
            'source_url' => 'https://example.com/b',
        ], 'gdelt');

        $this->assertEquals('low', $result['relevance_band']);
        $this->assertLessThan(0.35, $result['relevance_score']);
    }
}
