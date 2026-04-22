<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\GNewsFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class GNewsFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_maps_gnews_response(): void
    {
        config()->set('services.gnews.api_base_url', 'https://gnews.io/api/v4/search');
        config()->set('services.gnews.api_key', 'demo-key');
        Http::fake([
            'gnews.io/*' => Http::response([
                'articles' => [
                    [
                        'title' => 'Telkom umumkan ekspansi',
                        'url' => 'https://example.com/gnews1',
                        'publishedAt' => '2024-04-02T09:00:00Z',
                        'description' => 'TLKM ekspansi bisnis',
                        'content' => 'Konten',
                        'source' => ['name' => 'GNews'],
                        'language' => 'id',
                    ],
                ],
            ], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);
        $fetcher = new GNewsFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertNotEmpty($articles);
        $this->assertSame('gnews', $articles[0]['provider']);
        $this->assertSame('https://example.com/gnews1', $articles[0]['source_url']);
    }

    public function test_gnews_handles_error(): void
    {
        config()->set('services.gnews.api_base_url', 'https://gnews.io/api/v4/search');
        config()->set('services.gnews.api_key', 'demo-key');
        Http::fake([
            'gnews.io/*' => Http::response([], 500),
        ]);

        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);
        $fetcher = new GNewsFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertEmpty($articles);
    }

    public function test_gnews_handles_invalid_payload(): void
    {
        config()->set('services.gnews.api_base_url', 'https://gnews.io/api/v4/search');
        config()->set('services.gnews.api_key', 'demo-key');
        Http::fake([
            'gnews.io/*' => Http::response(['no_articles' => true], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);
        $fetcher = new GNewsFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertEmpty($articles);
    }

    public function test_gnews_queries_prioritize_exact_issuer_aliases_for_unvr(): void
    {
        $stock = Stock::factory()->create(['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk']);
        $fetcher = new class extends GNewsFetcher
        {
            public function exposedBuildQueries(Stock $stock): array
            {
                return $this->buildQueries($stock);
            }
        };

        $queries = $fetcher->exposedBuildQueries($stock);

        $this->assertContains('"Unilever Indonesia"', $queries);
        $this->assertTrue(collect($queries)->contains(fn ($query) => str_contains($query, '"PT Unilever Indonesia Tbk"')));
        $this->assertTrue(collect($queries)->contains(fn ($query) => str_contains($query, '"saham UNVR"')));
    }
}
