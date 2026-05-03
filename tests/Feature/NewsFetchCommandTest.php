<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Carbon\CarbonInterface;
use Tests\TestCase;

class NewsFetchCommandTest extends TestCase
{
    public function test_news_fetch_artisan_command_runs_without_exception(): void
    {
        $this->seedStock('BBCA');
        $this->app->instance(NewsAggregationService::class, new class extends NewsAggregationService {
            public function __construct() {}
            public function refreshFromProvider(Stock $stock, int $limit = 5, ?array $providerOverride = null): array
            {
                return $this->stats(['raw' => 1, 'saved' => 1, 'by_provider' => ['mock' => 1]]);
            }
            private function stats(array $override): array
            {
                return array_merge([
                    'raw' => 0, 'by_provider' => [], 'filtered' => 0, 'dropped_language' => 0,
                    'dropped_relevance' => 0, 'dropped_quality' => 0, 'dropped_exclusion' => 0,
                    'dropped_irrelevant' => 0, 'skipped_dedup' => 0, 'saved' => 0, 'updated' => 0,
                    'failed' => 0, 'kept_score_sum' => 0.0, 'kept_score_count' => 0,
                    'drop_score_sum' => 0.0, 'drop_score_count' => 0, 'band_high' => 0,
                    'band_medium' => 0, 'band_low' => 0, 'drop_relevance_sum' => 0.0,
                    'drop_entity_sum' => 0.0, 'drop_market_sum' => 0.0,
                    'kept_relevance_sum' => 0.0, 'kept_entity_sum' => 0.0, 'kept_market_sum' => 0.0,
                    'dropped_samples' => ['relevance' => [], 'quality' => [], 'exclusion' => []],
                ], $override);
            }
        });

        // Smoke test protects scheduler/queue deployments from broken command wiring.
        $this->artisan('news:fetch --stock=BBCA --limit=1')->assertExitCode(0);
    }

    public function test_news_fetch_ojk_saves_articles_with_null_stock_id(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->app->instance(NewsAggregationService::class, new class extends NewsAggregationService {
            public function __construct() {}
            public function refreshFromProvider(Stock $stock, int $limit = 5, ?array $providerOverride = null): array
            {
                NewsArticle::factory()->create([
                    'stock_id' => null,
                    'source_provider' => 'ojk_rss',
                    'title' => 'OJK pasar modal',
                ]);

                return [
                    'raw' => 1, 'by_provider' => ['ojk_rss' => 1], 'filtered' => 1,
                    'dropped_language' => 0, 'dropped_relevance' => 0, 'dropped_quality' => 0,
                    'dropped_exclusion' => 0, 'dropped_irrelevant' => 0, 'skipped_dedup' => 0,
                    'saved' => 1, 'updated' => 0, 'failed' => 0, 'kept_score_sum' => 1,
                    'kept_score_count' => 1, 'drop_score_sum' => 0, 'drop_score_count' => 0,
                    'band_high' => 1, 'band_medium' => 0, 'band_low' => 0,
                    'dropped_samples' => ['relevance' => [], 'quality' => [], 'exclusion' => []],
                ];
            }
            public function refreshOjkBackfill(Stock $stock, CarbonInterface|string $from, CarbonInterface|string $to, int $limit = 100, ?int $candidateLimit = null): array
            {
                return $this->refreshFromProvider($stock, $limit, ['ojk']);
            }
        });

        // OJK command should create global macro articles that backtest can include separately.
        $this->artisan('news:fetch-ojk --limit=1 --output-dir=storage/framework/testing')->assertExitCode(0);
        $this->assertDatabaseHas('news_articles', ['stock_id' => null, 'source_provider' => 'ojk_rss']);
        $this->assertDatabaseMissing('news_articles', ['stock_id' => $stock->id, 'source_provider' => 'ojk_rss']);
    }
}
