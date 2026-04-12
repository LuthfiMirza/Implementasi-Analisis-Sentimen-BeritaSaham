<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\RssLocalFetcher;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;

class RssLocalFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_parses_valid_rss(): void
    {
        Log::shouldReceive('warning')->byDefault();
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $rss = <<<XML
        <rss version="2.0">
          <channel>
            <title>Market</title>
            <item>
              <title>Bank Central Asia umumkan dividen</title>
              <link>https://example.com/a</link>
              <description>BBCA bagikan dividen</description>
              <pubDate>Mon, 01 Apr 2024 10:00:00 +0700</pubDate>
            </item>
          </channel>
        </rss>
        XML;
        Http::fake([
            '*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertEquals('Bank Central Asia umumkan dividen', $articles[0]['title']);
        $this->assertEquals('rss_local', $articles[0]['provider']);
    }

    public function test_skips_html_response(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        Http::fake([
            '*' => Http::response('<html>not rss</html>', 200, ['Content-Type' => 'text/html']),
        ]);

        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertEmpty($articles);
    }

    public function test_skips_malformed_xml(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        Http::fake([
            '*' => Http::response('<rss><channel><item><title>Broken', 200, ['Content-Type' => 'application/xml']),
        ]);

        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertEmpty($articles);
    }

    public function test_skips_empty_body(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        Http::fake([
            '*' => Http::response('', 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertEmpty($articles);
    }
}
