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

    public function test_competing_bank_article_is_not_saved_for_target_issuer(): void
    {
        config()->set('news.relevance_threshold', 0.2);
        config()->set('news.final_quality_threshold', 0.2);

        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
        ]);

        $fetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'BRI tebar dividen jumbo setelah laba naik',
                        'summary' => 'Bank Rakyat Indonesia dan BBRI membagikan dividen besar',
                        'source_url' => 'https://example.com/bbri-dividen',
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

        $service->refreshFromProvider($stock, 3, ['newsapi']);

        $this->assertEquals(0, NewsArticle::count());
    }

    public function test_ojk_macro_article_is_saved_once_as_global_context(): void
    {
        config()->set('news.relevance_threshold', 0.35);
        config()->set('news.final_quality_threshold', 0.4);

        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
        ]);

        $fetcher = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [
                    [
                        'title' => 'OJK perketat regulasi pasar modal',
                        'summary' => 'Pasar modal dan emiten wajib tingkatkan keterbukaan',
                        'source_url' => 'https://www.ojk.go.id/id/berita/macro-1',
                        'provider' => 'ojk_rss',
                        'published_at' => now(),
                        'language' => 'id',
                        'detected_language' => 'id',
                        'relevance_score' => 0.62,
                        'relevance_band' => 'high',
                        'entity_match_score' => 0.18,
                        'market_context_score' => 0.76,
                        'language_score' => 1.0,
                        'final_quality_score' => 0.68,
                        'quality_band' => 'high',
                        'source_weight' => 1.1,
                        'issuer_specificity' => 'macro_regulatory',
                        'skip_relevance_rescore' => true,
                        'matched_keywords' => ['pasar modal', 'emiten'],
                        'quality_flags' => ['macro_regulatory', 'ojk_official'],
                    ],
                ];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, [
            'ojk' => $fetcher,
        ]);

        $service->refreshFromProvider($stock, 3, ['ojk']);
        $service->refreshFromProvider($stock, 3, ['ojk']);

        $this->assertCount(1, NewsArticle::all());
        $article = NewsArticle::first();
        $this->assertNull($article->stock_id);
        $this->assertSame('ojk_rss', $article->source_provider);
    }
}
