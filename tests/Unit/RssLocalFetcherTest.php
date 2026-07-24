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

    public function test_default_feeds_are_expanded(): void
    {
        $fetcher = new class extends RssLocalFetcher
        {
            public function exposedFeeds(): array
            {
                return $this->feeds();
            }
        };

        $feeds = $fetcher->exposedFeeds();

        $this->assertContains('https://www.antaranews.com/rss/ekonomi-bisnis.xml', $feeds);
        $this->assertContains('https://www.antaranews.com/rss/ekonomi-bursa.xml', $feeds);
        $this->assertContains('https://www.kontan.co.id/feed', $feeds);
        $this->assertContains('https://www.bisnis.com/rss', $feeds);
        $this->assertContains('https://katadata.co.id/feed', $feeds);
        $this->assertContains('https://investor.id/rss', $feeds);
    }

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

    public function test_one_feed_timeout_does_not_abort_the_others(): void
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

        // One feed (of many) throwing a connection exception must not abort every other feed --
        // confirmed live: rss.tempo.co timing out silently discarded a full multi-provider fetch
        // for BBCA and TLKM because the original code had no try/catch around the per-feed call.
        Http::fake([
            'rss.tempo.co/*' => function () {
                throw new \Illuminate\Http\Client\ConnectionException('cURL error 28: Operation timed out');
            },
            '*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
    }
}
