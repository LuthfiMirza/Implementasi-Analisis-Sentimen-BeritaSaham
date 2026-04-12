<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Analytics\SentimentComparisonService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SentimentComparisonServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_correlation_and_signal_outputs_present(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        for ($i = 0; $i < 6; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::now()->subDays(6 - $i),
                'close' => 1000 + ($i * 2),
                'interval_type' => '1d',
            ]);
        }

        for ($i = 0; $i < 5; $i++) {
            NewsArticle::factory()->create([
                'stock_id' => $stock->id,
                'title' => 'BBCA berita '.$i,
                'sentiment_label' => $i % 2 === 0 ? 'positive' : 'negative',
                'sentiment_score' => $i % 2 === 0 ? 0.4 : -0.3,
                'relevance_score' => 0.8,
                'source_weight' => 1.0,
                'published_at' => Carbon::now()->subDays(5 - $i),
            ]);
        }

        $service = $this->app->make(SentimentComparisonService::class);
        $report = $service->evaluate($stock, 7);

        $this->assertArrayHasKey('correlation', $report);
        $this->assertArrayHasKey('signal_backtest', $report);
        $this->assertEquals('BBCA', $report['stock']);
    }
}
