<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\GdeltFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class GdeltFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_maps_gdelt_response(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response([
                'articles' => [
                    [
                        'title' => 'BBCA catat laba bersih naik',
                        'url' => 'https://example.com/bbca-laba',
                        'seendate' => '20260420T090000Z',
                        'excerpt' => 'BBCA laba naik',
                        'snippet' => 'Konten',
                        'sourceCommonName' => 'Example News',
                    ],
                ],
            ], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertNotEmpty($articles);
        $this->assertSame('https://example.com/bbca-laba', $articles[0]['source_url']);
    }

    public function test_gdelt_timeout_does_not_throw(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => function () {
                throw new \Illuminate\Http\Client\ConnectionException('cURL error 28: Connection timed out');
            },
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertSame([], $articles);
    }

    public function test_gdelt_handles_error_response(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response([], 500),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertSame([], $articles);
    }

    public function test_gdelt_handles_invalid_payload(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response(['no_articles' => true], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertSame([], $articles);
    }

    public function test_gdelt_wraps_or_chain_query_in_parentheses(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response(['articles' => []], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $fetcher->fetchForStock($stock, 3);

        Http::assertSent(function (\Illuminate\Http\Client\Request $request) {
            $query = $request->data()['query'] ?? '';

            // GDELT rejects a bare "A OR B" chain once followed by "AND (...)" -- the
            // keyword OR-chain must be parenthesized before the language filter is appended.
            return str_starts_with($query, '(') && str_contains($query, ') AND (sourcelang:');
        });
    }

    public function test_gdelt_drops_quoted_phrases_shorter_than_four_chars(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response(['articles' => []], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new GdeltFetcher();
        $fetcher->fetchForStock($stock, 3);

        Http::assertSent(function (\Illuminate\Http\Client\Request $request) {
            $query = $request->data()['query'] ?? '';

            // GDELT rejects quoted phrases under 4 chars ("The specified phrase is too
            // short") -- StockKeywordMapper's own "BCA" alias must not survive into the request.
            return ! str_contains($query, '"BCA"') && str_contains($query, '"BBCA"');
        });
    }

    public function test_gdelt_historical_wraps_or_chain_query_in_parentheses(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response(['articles' => []], 200),
        ]);

        $fetcher = new GdeltFetcher();
        $fetcher->fetchHistorical(
            '"Bank Central Asia" OR "BBCA" OR "Bank BCA"',
            \Carbon\Carbon::parse('2026-01-01'),
            \Carbon\Carbon::parse('2026-01-31')
        );

        Http::assertSent(function (\Illuminate\Http\Client\Request $request) {
            $query = $request->data()['query'] ?? '';

            return str_starts_with($query, '(') && str_contains($query, ') AND (sourcelang:');
        });
    }
}
