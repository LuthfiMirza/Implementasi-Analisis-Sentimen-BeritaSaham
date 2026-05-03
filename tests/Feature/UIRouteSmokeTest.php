<?php

namespace Tests\Feature;

use App\Services\Analytics\BacktestService;
use App\Services\Prediction\ResearchRankingService;
use Tests\TestCase;

class UIRouteSmokeTest extends TestCase
{
    public function test_authenticated_user_ui_routes_return_200(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 60);
        $this->seedArticle($stock, ['title' => 'BBCA article listing smoke']);
        $this->bindUiFakes();
        $this->actingAsUser();

        // These are primary Blade screens; smoke tests catch broken view dependencies.
        foreach (['/dashboard', '/news', '/watchlist', '/analytics?code=BBCA&period=30', '/backtest', '/trades'] as $uri) {
            $this->get($uri)->assertOk();
        }
    }

    public function test_guest_ui_routes_redirect_to_login(): void
    {
        // Non-public screens should consistently use auth middleware.
        foreach (['/dashboard', '/news', '/watchlist', '/analytics?code=BBCA&period=30', '/backtest', '/trades', '/admin/stocks'] as $uri) {
            $this->get($uri)->assertRedirect('/login');
        }
    }

    public function test_dashboard_contains_sentimena_keyword(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 40);
        $this->seedArticle($stock);

        // Brand/market summary copy confirms the dashboard view rendered, not just status code.
        $this->actingAsUser()->get('/dashboard')->assertOk()->assertSee('Sentimena', false);
    }

    public function test_news_page_contains_seeded_article_listing(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedArticle($stock, ['title' => 'BBCA article listing smoke']);

        // News list should render actual rows from the database.
        $this->actingAsUser()->get('/news')->assertOk()->assertSee('BBCA article listing smoke');
    }

    public function test_admin_routes_return_403_for_regular_user_and_200_for_admin(): void
    {
        // Requirement says regular users receive 403; admin users receive CRUD access.
        $this->actingAsUser()->get('/admin/stocks')->assertForbidden();
        $this->actingAsAdmin()->get('/admin/stocks')->assertOk();
    }

    // Previously documented as a contract gap. Routes are now registered.
    // Verifies: /predictions accessible to all auth users, /admin/users protected by AdminMiddleware.
    public function test_predictions_and_admin_users_routes_are_now_registered(): void
    {
        $this->actingAsUser()->get('/predictions')->assertOk();
        $this->actingAsAdmin()->get('/predictions')->assertOk();
        $this->actingAsUser()->get('/admin/users')->assertForbidden();
        $this->actingAsAdmin()->get('/admin/users')->assertOk();
    }

    private function bindUiFakes(): void
    {
        $this->app->instance(ResearchRankingService::class, new class extends ResearchRankingService {
            public function __construct() {}
            public function getRanking(array $stockCodes): array
            {
                return ['available' => false, 'ranked' => [], 'message' => 'test'];
            }
        });
        $this->app->instance(BacktestService::class, new class extends BacktestService {
            public function __construct() {}
            public function runForStock($stock, int $lookback = 60, int $forward = 5, int $step = 5, float $threshold = 1.0, bool $includeMacroNews = true, ?bool $macroRegulatorySignal = null, int $maxWindows = 80): array
            {
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
                        'confidence' => 0.8,
                        'is_correct' => true,
                    ]],
                ];
            }
        });
    }
}
