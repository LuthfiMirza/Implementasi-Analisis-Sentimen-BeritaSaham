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

    public function test_comparison_can_include_or_exclude_macro_news(): void
    {
        config(['analytics.macro_regulatory_signal.enabled' => true]);

        $stock = Stock::factory()->create(['code' => 'BBRI', 'company_name' => 'Bank Rakyat Indonesia']);

        for ($i = 0; $i < 8; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::parse('2026-04-08')->addDays($i),
                'close' => 1000 + ($i * 3),
                'interval_type' => '1d',
            ]);
        }

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BBRI ekspansi kredit',
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.4,
            'published_at' => now()->subDays(2),
        ]);

        NewsArticle::factory()->create([
            'stock_id' => null,
            'source_provider' => 'ojk_rss',
            'title' => 'OJK perkuat pengawasan emiten',
            'summary' => 'Penguatan pengawasan pasar modal dan emiten diumumkan OJK.',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'published_at' => now()->subDays(2),
        ]);

        $service = $this->app->make(SentimentComparisonService::class);
        $withMacro = $service->evaluate($stock, 7, true);
        $withoutMacro = $service->evaluate($stock, 7, false);

        $this->assertSame(2, $withMacro['data_points']['article_count']);
        $this->assertSame(1, $withoutMacro['data_points']['article_count']);
        $this->assertTrue($withMacro['data_points']['include_macro_news']);
        $this->assertFalse($withoutMacro['data_points']['include_macro_news']);
        $this->assertArrayHasKey('macro_regulatory', $withMacro);
        $this->assertTrue($withMacro['macro_regulatory']['enabled']);
    }
}
