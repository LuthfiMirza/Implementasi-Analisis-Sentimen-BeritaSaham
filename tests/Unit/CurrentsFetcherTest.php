<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\CurrentsFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class CurrentsFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_maps_currents_response(): void
    {
        config()->set('services.currents.api_key', 'demo-key');
        Http::fake([
            'api.currentsapi.services/*' => Http::response([
                'status' => 'ok',
                'news' => [
                    [
                        'id' => 'abc-123',
                        'title' => 'BBCA catat laba bersih naik',
                        'description' => 'BBCA laba naik kuartal ini',
                        'url' => 'https://example.com/bbca-laba',
                        'author' => 'Example News',
                        'language' => 'id',
                        'category' => ['business'],
                        'published' => '2026-04-02 09:00:00 +0000',
                    ],
                ],
            ], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new CurrentsFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('currents', $articles[0]['provider']);
        $this->assertSame('https://example.com/bbca-laba', $articles[0]['source_url']);
    }

    public function test_returns_empty_without_api_key(): void
    {
        config()->set('services.currents.api_key', null);
        Http::fake();

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new CurrentsFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertSame([], $articles);
        Http::assertNothingSent();
    }

    public function test_currents_handles_error_response(): void
    {
        config()->set('services.currents.api_key', 'demo-key');
        Http::fake([
            'api.currentsapi.services/*' => Http::response([], 500),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new CurrentsFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertSame([], $articles);
    }

    public function test_currents_handles_request_exception(): void
    {
        config()->set('services.currents.api_key', 'demo-key');
        Http::fake([
            'api.currentsapi.services/*' => function () {
                throw new \Illuminate\Http\Client\ConnectionException('cURL error 28: timed out');
            },
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new CurrentsFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertSame([], $articles);
    }

    public function test_currents_handles_invalid_payload(): void
    {
        config()->set('services.currents.api_key', 'demo-key');
        Http::fake([
            'api.currentsapi.services/*' => Http::response(['status' => 'ok'], 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new CurrentsFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertSame([], $articles);
    }
}
