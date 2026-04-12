<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use App\Services\News\NewsFetcherInterface;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class NewsQualityBackfillTest extends TestCase
{
    use RefreshDatabase;

    public function test_provider_fallback_is_applied(): void
    {
        config()->set('services.news.provider', 'multi');

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        $fetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'BBCA rilis kinerja',
                        'summary' => 'Bank Central Asia catat laba',
                        'source_url' => 'https://example.com/bbca',
                        'published_at' => now(),
                        // provider sengaja dikosongkan
                    ],
                ];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, [
            'finnhub' => $fetcher,
        ]);

        $service->refreshFromProvider($stock, 3, ['finnhub']);

        $article = NewsArticle::first();
        $this->assertNotNull($article);
        $this->assertEquals('finnhub', $article->source_provider);
        $this->assertNotNull($article->final_quality_score);
    }

    public function test_rescore_command_fills_missing_quality_fields(): void
    {
        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);

        $article = NewsArticle::factory()->for($stock)->create([
            'source_provider' => null,
            'relevance_score' => null,
            'final_quality_score' => null,
            'quality_band' => null,
            'raw_payload' => ['provider' => 'gnews'],
        ]);

        Artisan::call('news:rescore-quality', [
            '--stock' => $stock->code,
            '--force' => true,
            '--days' => 400,
        ]);

        $article->refresh();

        $this->assertNotNull($article->final_quality_score);
        $this->assertNotNull($article->quality_band);
        $this->assertEquals('gnews', $article->source_provider);
        $this->assertNotNull($article->relevance_score);
    }

    public function test_strong_article_can_reach_high_after_tuning(): void
    {
        config()->set('news.quality_high', 0.65);
        config()->set('news.quality_medium', 0.45);
        config()->set('news.final_quality_threshold', 0.32);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $service = new \App\Services\News\RelevanceScoringService(new \App\Services\News\StockKeywordMapper());

        $raw = [
            'title' => 'Bank Central Asia catat laba dan bagi dividen',
            'summary' => 'BBCA merilis laporan laba dan dividen, kinerja bank positif',
            'source_url' => 'https://example.com/bbca-high',
            'language' => 'id',
            'provider' => 'newsapi',
        ];

        $score = $service->score($stock, $raw, 'newsapi');
        $this->assertGreaterThanOrEqual(config('news.quality_high'), $score['final_quality_score']);
        $this->assertEquals('high', $score['quality_band']);
    }
}
