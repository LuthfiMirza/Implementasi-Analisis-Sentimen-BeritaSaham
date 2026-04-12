<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Services\News\RssLocalFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class RssLocalFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_invalid_html_feed_is_skipped(): void
    {
        config()->set('news.rss_timeout', 3);
        putenv('NEWS_RSS_SOURCES=https://invalid.test/feed');

        Http::fake([
            '*' => Http::response('<html>not rss</html>', 200, ['Content-Type' => 'text/html']),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $fetcher = new RssLocalFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertCount(0, $articles);
    }
}
