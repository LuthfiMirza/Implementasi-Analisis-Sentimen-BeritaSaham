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
}
