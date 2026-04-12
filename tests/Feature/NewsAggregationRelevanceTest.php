<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use App\Services\News\NewsFetcherInterface;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NewsAggregationRelevanceTest extends TestCase
{
    use RefreshDatabase;

    public function test_low_relevance_articles_are_dropped_and_deduped(): void
    {
        config()->set('services.news.provider', 'multi');
        config()->set('news.relevance_threshold', 0.35);
        config()->set('news.source_priority', ['newsapi', 'gnews']);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        $highFetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'Bank Central Asia catat laba',
                        'summary' => 'BBCA laba tumbuh',
                        'source_url' => 'https://example.com/a',
                        'provider' => 'newsapi',
                        'published_at' => now(),
                    ],
                ];
            }
        };

        $lowFetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'Cuaca hari ini cerah',
                        'summary' => 'Tidak terkait saham',
                        'source_url' => 'https://example.com/a', // duplikat URL harus dedup
                        'provider' => 'gnews',
                        'published_at' => now(),
                    ],
                ];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, [
            'newsapi' => $highFetcher,
            'gnews' => $lowFetcher,
        ]);

        $service->refreshFromProvider($stock, 3);

        $this->assertEquals(1, NewsArticle::count());
        $article = NewsArticle::first();
        $this->assertEquals('https://example.com/a', $article->source_url);
        $this->assertEquals('newsapi', $article->source_provider);
        $this->assertTrue($article->relevance_score >= 0.35);
    }
}
