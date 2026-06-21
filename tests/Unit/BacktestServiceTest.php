<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Analytics\BacktestService;
use App\Services\Analytics\DecisionSupportService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Collection;
use Tests\TestCase;

class BacktestServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_backtest_can_include_or_exclude_macro_news(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $startDate = Carbon::parse('2026-03-01', 'Asia/Jakarta');

        for ($i = 0; $i < 40; $i++) {
            $close = 1000 + ($i * 5);
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => $startDate->copy()->addDays($i),
                'open' => $close - 2,
                'high' => $close + 5,
                'low' => $close - 5,
                'close' => $close,
                'volume' => 1_000_000 + ($i * 1000),
                'interval_type' => '1d',
            ]);
        }

        NewsArticle::factory()->create([
            'stock_id' => null,
            'source_provider' => 'ojk_rss',
            'title' => 'OJK perkuat pasar modal dan perlindungan investor',
            'summary' => 'Pasar modal, emiten, dan investor tetap menjadi fokus penguatan regulasi.',
            'content_snippet' => 'Pasar modal, emiten, dan investor tetap menjadi fokus penguatan regulasi.',
            'full_text' => 'Pasar modal, emiten, dan investor tetap menjadi fokus penguatan regulasi.',
            'published_at' => Carbon::parse('2026-03-20', 'Asia/Jakarta'),
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'relevance_score' => 0.62,
            'final_quality_score' => 0.68,
            'source_weight' => 1.1,
        ]);

        $dss = new class extends DecisionSupportService
        {
            public function __construct()
            {
            }

            public function analyze(\App\Models\Stock $stock, Collection $prices, Collection $articles, ?array $analytics = null): array
            {
                $hasMacro = $articles->contains(fn ($article) => $article->source_provider === 'ojk_rss');

                return [
                    'prediction' => $hasMacro ? 'down' : 'flat',
                    'prediction_confidence' => 0.6,
                    'final_score' => $hasMacro ? 0.75 : 0.1,
                    'sentiment_average' => 0.0,
                ];
            }
        };

        $service = new BacktestService($dss);

        $withMacro = $service->runForStock($stock, 30, 5, 5, 1.0, true);
        $withoutMacro = $service->runForStock($stock, 30, 5, 5, 1.0, false);

        $this->assertSame('down', $withMacro['results'][0]['prediction']);
        $this->assertSame('flat', $withoutMacro['results'][0]['prediction']);
        $this->assertTrue($withMacro['params']['includeMacroNews']);
        $this->assertFalse($withoutMacro['params']['includeMacroNews']);
    }

    public function test_backtest_uses_canonical_prices_when_duplicate_trade_dates_exist(): void
    {
        $stock = Stock::factory()->create(['code' => 'DEWA', 'company_name' => 'Darma Henwa']);
        $startDate = Carbon::parse('2026-03-01', 'Asia/Jakarta');

        for ($i = 0; $i < 40; $i++) {
            $date = $startDate->copy()->addDays($i);
            $close = 400 + $i;
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => $date,
                'open' => $close - 2,
                'high' => $close + 5,
                'low' => $close - 5,
                'close' => $close,
                'volume' => 900_000_000,
                'interval_type' => '1d',
                'source' => null,
            ]);

            if ($i >= 30 && $i <= 35) {
                StockPrice::factory()->create([
                    'stock_id' => $stock->id,
                    'price_date' => $date->copy()->setTime(15, 0),
                    'open' => 45,
                    'high' => 50,
                    'low' => 40,
                    'close' => 47.21,
                    'volume' => 2_000_000,
                    'interval_type' => '1d',
                    'source' => 'seed',
                ]);
            }
        }

        $dss = new class extends DecisionSupportService
        {
            public function __construct()
            {
            }

            public function analyze(\App\Models\Stock $stock, Collection $prices, Collection $articles, ?array $analytics = null): array
            {
                return [
                    'prediction' => 'up',
                    'prediction_confidence' => 0.6,
                    'final_score' => 0.7,
                    'sentiment_average' => 0.0,
                ];
            }
        };

        $service = new BacktestService($dss);
        $result = $service->runForStock($stock, 30, 5, 1, 1.0, false, null, 4);

        $this->assertArrayNotHasKey('error', $result);
        $this->assertCount(4, $result['results']);
        foreach ($result['results'] as $row) {
            $this->assertLessThan(5.0, abs($row['actual_return']));
        }
    }
}
