<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use App\Services\News\NewsFetcherInterface;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArticleDeduplicationTest extends TestCase
{
    use RefreshDatabase;

    public function test_same_url_deduped_once(): void
    {
        config()->set('services.news.provider', 'multi');
        config()->set('news.relevance_threshold', 0.0);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        $fetcherA = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'Bank Central Asia catat laba',
                    'summary' => 'BBCA laba',
                    'source_url' => 'https://example.com/same',
                    'provider' => 'newsapi',
                    'published_at' => now(),
                ]];
            }
        };

        $fetcherB = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'Bank Central Asia catat laba',
                    'summary' => 'BBCA laba',
                    'source_url' => 'https://example.com/same',
                    'provider' => 'gnews',
                    'published_at' => now(),
                ]];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, ['newsapi' => $fetcherA, 'gnews' => $fetcherB]);

        $service->refreshFromProvider($stock, 5);

        $this->assertEquals(1, NewsArticle::count());
    }

    public function test_normalized_title_dedup_when_no_url(): void
    {
        config()->set('services.news.provider', 'multi');
        config()->set('news.relevance_threshold', 0.0);

        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);

        $fetcherA = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'Telkom Indonesia umumkan ekspansi',
                    'summary' => 'Ekspansi bisnis',
                    'provider' => 'newsapi',
                    'published_at' => now(),
                ]];
            }
        };

        $fetcherB = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'Telkom  indonesia  umumkan  ekspansi!!',
                    'summary' => 'Berita serupa',
                    'provider' => 'gnews',
                    'published_at' => now(),
                ]];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, ['newsapi' => $fetcherA, 'gnews' => $fetcherB]);

        $service->refreshFromProvider($stock, 5);

        $this->assertEquals(1, NewsArticle::count());
    }

    public function test_similar_but_different_titles_are_not_deduped(): void
    {
        config()->set('services.news.provider', 'multi');
        config()->set('news.relevance_threshold', 0.0);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        $fetcherA = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'BCA catat laba bersih',
                    'summary' => 'Laba bersih tumbuh',
                    'provider' => 'newsapi',
                    'published_at' => now(),
                ]];
            }
        };

        $fetcherB = new class implements NewsFetcherInterface {
            public function fetchForStock(\App\Models\Stock $stock, int $limit = 5): array
            {
                return [[
                    'title' => 'BCA umumkan dividen interim',
                    'summary' => 'Dividen berbeda topik',
                    'provider' => 'gnews',
                    'published_at' => now(),
                ]];
            }
        };

        $service = new NewsAggregationService();
        $ref = new \ReflectionClass($service);
        $prop = $ref->getProperty('fetchers');
        $prop->setAccessible(true);
        $prop->setValue($service, ['newsapi' => $fetcherA, 'gnews' => $fetcherB]);

        $service->refreshFromProvider($stock, 5);

        $this->assertEquals(2, NewsArticle::count());
    }
}
