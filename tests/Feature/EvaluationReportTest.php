<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Analytics\EvaluationReportService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class EvaluationReportTest extends TestCase
{
    use RefreshDatabase;

    public function test_evaluation_report_returns_metrics(): void
    {
        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom']);

        for ($i = 0; $i < 4; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::now()->subDays(4 - $i),
                'close' => 1000 + ($i * 5),
                'interval_type' => '1d',
            ]);
        }

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'Laba tumbuh kuat',
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.6,
            'sentiment_confidence' => 0.9,
            'sentiment_method' => 'python',
            'published_at' => Carbon::now()->subDay(),
        ]);

        $service = $this->app->make(EvaluationReportService::class);
        $report = $service->generate($stock, 7);

        $this->assertArrayHasKey('sentiment', $report);
        $this->assertArrayHasKey('analytics', $report);
        $this->assertNotEmpty($report['prediction']['method'] ?? null);
        $this->assertSame('TLKM', $report['stock']['code']);
    }

    public function test_evaluation_report_can_include_or_exclude_macro_news(): void
    {
        config(['analytics.macro_regulatory_signal.enabled' => true]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        for ($i = 0; $i < 5; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::parse('2026-04-10')->addDays($i),
                'close' => 900 + ($i * 10),
                'interval_type' => '1d',
            ]);
        }

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BBCA catat kinerja positif',
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.5,
            'published_at' => Carbon::parse('2026-04-14'),
        ]);

        NewsArticle::factory()->create([
            'stock_id' => null,
            'source_provider' => 'ojk_rss',
            'title' => 'OJK perkuat integritas pasar modal',
            'summary' => 'Pasar modal dan emiten mendapat penguatan regulasi.',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'published_at' => Carbon::parse('2026-04-14'),
        ]);

        $service = $this->app->make(EvaluationReportService::class);
        $withMacro = $service->generate($stock, 7, true);
        $withoutMacro = $service->generate($stock, 7, false);

        $this->assertSame(2, $withMacro['data_points']['article_count']);
        $this->assertSame(1, $withoutMacro['data_points']['article_count']);
        $this->assertTrue($withMacro['data_points']['include_macro_news']);
        $this->assertFalse($withoutMacro['data_points']['include_macro_news']);
        $this->assertArrayHasKey('macro_regulatory', $withMacro);
        $this->assertTrue($withMacro['macro_regulatory']['enabled']);
        $this->assertTrue($withMacro['macro_regulatory']['active']);
    }

    public function test_evaluation_report_remains_stable_when_macro_regulatory_signal_is_disabled(): void
    {
        config(['analytics.macro_regulatory_signal.enabled' => false]);

        $stock = Stock::factory()->create(['code' => 'BBRI', 'company_name' => 'Bank Rakyat Indonesia']);

        for ($i = 0; $i < 5; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::parse('2026-04-10')->addDays($i),
                'close' => 1000 + ($i * 10),
                'interval_type' => '1d',
            ]);
        }

        NewsArticle::factory()->create([
            'stock_id' => null,
            'source_provider' => 'ojk_rss',
            'title' => 'OJK perketat pengawasan pasar modal',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'published_at' => Carbon::parse('2026-04-14'),
        ]);

        $service = $this->app->make(EvaluationReportService::class);
        $report = $service->generate($stock, 7, true, false);

        $this->assertArrayHasKey('macro_regulatory', $report);
        $this->assertFalse($report['macro_regulatory']['enabled']);
    }
}
