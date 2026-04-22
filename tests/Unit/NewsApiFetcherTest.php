<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\NewsApiFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class NewsApiFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_maps_newsapi_response(): void
    {
        config()->set('services.news.api_base_url', 'https://newsapi.org/v2/everything');
        config()->set('services.news.api_key', 'demo-key');
        Http::fake([
            'newsapi.org/*' => Http::response([
                'articles' => [
                    [
                        'title' => 'Bank Central Asia catat laba',
                        'url' => 'https://example.com/news1',
                        'publishedAt' => '2024-04-01T10:00:00Z',
                        'description' => 'BBCA laba tumbuh',
                        'content' => 'Isi konten',
                        'source' => ['name' => 'Example'],
                    ],
                ],
            ], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new NewsApiFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertNotEmpty($articles);
        $this->assertSame('newsapi', $articles[0]['provider']);
        $this->assertSame('https://example.com/news1', $articles[0]['source_url']);
        $this->assertEquals('Bank Central Asia catat laba', $articles[0]['title']);
    }

    public function test_newsapi_handles_error_and_returns_empty(): void
    {
        config()->set('services.news.api_base_url', 'https://newsapi.org/v2/everything');
        config()->set('services.news.api_key', 'demo-key');
        Http::fake([
            'newsapi.org/*' => Http::response([], 500),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new NewsApiFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertEmpty($articles);
    }

    public function test_newsapi_handles_invalid_payload(): void
    {
        config()->set('services.news.api_base_url', 'https://newsapi.org/v2/everything');
        config()->set('services.news.api_key', 'demo-key');
        Http::fake([
            'newsapi.org/*' => Http::response(['unexpected' => 'value'], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new NewsApiFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertEmpty($articles);
    }

    public function test_newsapi_queries_prioritize_exact_issuer_aliases_for_icbp(): void
    {
        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new class extends NewsApiFetcher
        {
            public function exposedBuildQueries(Stock $stock): array
            {
                return $this->buildQueries($stock);
            }
        };

        $queries = $fetcher->exposedBuildQueries($stock);

        $this->assertContains('"Indofood CBP Sukses Makmur"', $queries);
        $this->assertTrue(collect($queries)->contains(fn ($query) => str_contains($query, '"PT Indofood CBP Sukses Makmur Tbk"')));
        $this->assertTrue(collect($queries)->contains(fn ($query) => str_contains($query, '"saham ICBP"')));
    }
}
