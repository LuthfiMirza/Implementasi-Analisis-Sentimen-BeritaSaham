<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\RelevanceScoringService;
use App\Services\News\StockKeywordMapper;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RelevanceScoringThresholdTest extends TestCase
{
    use RefreshDatabase;

    public function test_strong_alias_passes_relevance_threshold(): void
    {
        config()->set('news.relevance_threshold', 0.35);
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $scorer = new RelevanceScoringService(new StockKeywordMapper());

        $raw = [
            'title' => 'Bank Central Asia umumkan kenaikan laba',
            'summary' => 'BBCA mencatat pertumbuhan laba dan dividen',
            'language' => 'id',
        ];

        $score = $scorer->score($stock, $raw, 'newsapi');
        $this->assertGreaterThanOrEqual(config('news.relevance_threshold'), $score['relevance_score']);
    }

    public function test_ambiguous_goto_still_penalized(): void
    {
        $stock = Stock::factory()->create(['code' => 'GOTO', 'company_name' => 'GoTo Gojek Tokopedia']);
        $scorer = new RelevanceScoringService(new StockKeywordMapper());

        $raw = [
            'title' => 'Wisata ke Goto Islands Jepang',
            'summary' => 'Liburan ke pulau goto',
            'language' => 'en',
        ];

        $score = $scorer->score($stock, $raw, 'newsapi');
        $this->assertLessThan(config('news.relevance_threshold'), $score['relevance_score']);
    }
}
