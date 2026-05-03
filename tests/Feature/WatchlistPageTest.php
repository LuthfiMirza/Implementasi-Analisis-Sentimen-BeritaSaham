<?php

namespace Tests\Feature;

use App\Services\Prediction\ResearchRankingService;
use Tests\TestCase;

class WatchlistPageTest extends TestCase
{
    public function test_watchlist_page_returns_200_for_authenticated_user(): void
    {
        $this->seedStock('BBCA');
        $this->app->instance(ResearchRankingService::class, new class extends ResearchRankingService {
            public function __construct() {}
            public function getRanking(array $stockCodes): array
            {
                return ['available' => false, 'ranked' => [], 'message' => 'test'];
            }
        });

        // Watchlist is a protected user workflow, not an admin-only page.
        $this->actingAsUser()->get('/watchlist')->assertOk();
    }
}
