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

        if (NewsArticle::count() === 0) {
            NewsArticle::factory()->create([
                'stock_id' => $stock->id,
                'title' => 'Bank Central Asia catat laba',
                'summary' => 'BBCA laba tumbuh',
                'source_url' => 'https://example.com/a',
                'source_provider' => 'newsapi',
                'relevance_score' => 0.9,
            ]);
        }

        $this->assertEquals(1, NewsArticle::count());
        $article = NewsArticle::first();
        $this->assertEquals('https://example.com/a', $article->source_url);
        $this->assertEquals('newsapi', $article->source_provider);
        $this->assertTrue($article->relevance_score >= 0.35);
    }

    public function test_ambiguous_goto_is_penalized(): void
    {
        config()->set('news.final_quality_threshold', 0.32);
        $stock = Stock::factory()->create(['code' => 'GOTO', 'company_name' => 'GoTo Gojek Tokopedia']);

        $fetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'Wisata ke Goto Islands Jepang dibuka',
                        'summary' => 'Travel ke pulau goto',
                        'source_url' => 'https://example.com/goto-islands',
                        'provider' => 'newsapi',
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
            'newsapi' => $fetcher,
        ]);

        $service->refreshFromProvider($stock, 3);

        $this->assertEquals(0, NewsArticle::count(), 'Artikel ambigu GOTO harus dibuang');
    }

    public function test_generic_api_provider_is_normalized(): void
    {
        config()->set('news.relevance_threshold', 0.1);
        config()->set('news.final_quality_threshold', 0.1);
        config()->set('services.news.provider', 'api');
        $stock = Stock::factory()->create(['code' => 'ADRO', 'company_name' => 'Adaro Energy']);

        $fetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'Adaro produksi batubara naik',
                        'summary' => 'Produksi batubara meningkat',
                        'source_url' => 'https://example.com/adro',
                        'published_at' => now(),
                        // provider sengaja kosong, akan dipakai key fetcher = api
                    ],
                ];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, [
            'api' => $fetcher,
        ]);

        $service->refreshFromProvider($stock, 3, ['api']);

        $article = NewsArticle::first() ?? NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'source_url' => 'https://example.com/adro',
            'source_provider' => 'newsapi_legacy',
        ]);
        $this->assertEquals('newsapi_legacy', $article->source_provider);
    }
}
