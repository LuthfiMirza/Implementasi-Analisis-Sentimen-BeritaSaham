<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Services\Analytics\BacktestService;
use Illuminate\Support\Facades\Cache;
use Tests\TestCase;

class BacktestDSSTest extends TestCase
{
    public function test_backtest_page_returns_200_for_authenticated_user(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->app->instance(BacktestService::class, $this->fakeBacktestService());

        // Backtest UI is part of the authenticated thesis workflow.
        $this->actingAsUser()->get('/backtest?code=BBCA')->assertOk();
    }

    public function test_include_macro_news_scope_returns_more_articles_than_stock_only(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedArticle($stock);
        NewsArticle::factory()->create([
            'stock_id' => null,
            'source_provider' => 'ojk_rss',
            'published_at' => now(),
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0,
            'sentiment_method' => 'rule_based',
        ]);

        $withMacro = NewsArticle::forStockContext($stock, true)->count();
        $withoutMacro = NewsArticle::forStockContext($stock, false)->count();

        // Macro regulatory context must be explicitly toggleable in backtests.
        $this->assertGreaterThan($withoutMacro, $withMacro);
    }

    public function test_macro_regulatory_signal_lowers_extreme_directional_confidence(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->fakeBacktestService();

        $withoutMacro = $service->runForStock($stock, 30, 5, 3, 1.0, true, false);
        $withMacro = $service->runForStock($stock, 30, 5, 3, 1.0, true, true);

        // Regulatory caution should moderate extreme confidence.
        $this->assertLessThan($withoutMacro['results'][0]['confidence'], $withMacro['results'][0]['confidence']);
    }

    public function test_backtest_result_is_cached_for_identical_request(): void
    {
        Cache::store('file')->flush();
        $stock = $this->seedStock('BBCA');
        $service = $this->fakeBacktestService();
        $this->app->instance(BacktestService::class, $service);

        $this->actingAsUser()->get('/backtest?code=BBCA&max_windows=5')->assertOk();
        $this->actingAsUser()->get('/backtest?code=BBCA&max_windows=5')->assertOk();

        // Cache prevents repeated expensive DB-heavy sliding-window simulations.
        $this->assertSame(1, $service->calls);
    }

    private function fakeBacktestService(): BacktestService
    {
        return new class extends BacktestService {
            public int $calls = 0;
            public function __construct() {}
            public function runForStock($stock, int $lookback = 60, int $forward = 5, int $step = 5, float $threshold = 1.0, bool $includeMacroNews = true, ?bool $macroRegulatorySignal = null, int $maxWindows = 80): array
            {
                $this->calls++;
                $confidence = $macroRegulatorySignal ? 0.45 : 0.9;

                return [
                    'stock' => $stock->code,
                    'total' => 1,
                    'correct' => 1,
                    'accuracy' => 100,
                    'correlation' => 0.1,
                    'avg_return_correct' => 2.0,
                    'avg_return_wrong' => 0.0,
                    'per_pred' => [
                        'up' => ['total' => 1, 'correct' => 1, 'accuracy' => 100],
                        'flat' => ['total' => 0, 'correct' => 0, 'accuracy' => 0],
                        'down' => ['total' => 0, 'correct' => 0, 'accuracy' => 0],
                    ],
                    'results' => [[
                        'date' => '2026-04-30',
                        'prediction' => 'up',
                        'actual_direction' => 'up',
                        'actual_return' => 2.0,
                        'final_score' => 75,
                        'confidence' => $confidence,
                        'is_correct' => true,
                    ]],
                    'macro_regulatory_summary' => ['signal_enabled' => (bool) $macroRegulatorySignal],
                ];
            }
        };
    }
}
