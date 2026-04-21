<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\GoogleNewsRssFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class GoogleNewsRssFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_maps_google_news_rss_response(): void
    {
        $rss = <<<'XML'
        <rss version="2.0">
          <channel>
            <item>
              <title>Unilever Indonesia bagikan dividen interim</title>
              <link>https://news.google.com/rss/articles/abc123</link>
              <description>UNVR membagikan dividen interim untuk pemegang saham.</description>
              <pubDate>Tue, 21 Apr 2026 08:00:00 +0700</pubDate>
              <source url="https://www.cnbcindonesia.com">CNBC Indonesia</source>
            </item>
          </channel>
        </rss>
        XML;

        Http::fake([
            'news.google.com/*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $stock = Stock::factory()->create(['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk']);
        $fetcher = new GoogleNewsRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('google_news_rss', $articles[0]['provider']);
        $this->assertSame('CNBC Indonesia', $articles[0]['source_name']);
        $this->assertStringContainsString('Unilever Indonesia', $articles[0]['title']);
    }

    public function test_google_news_rss_queries_use_exact_issuer_terms(): void
    {
        Http::fake([
            'news.google.com/*' => Http::response('<rss><channel></channel></rss>', 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new GoogleNewsRssFetcher();
        $fetcher->fetchForStock($stock, 5);

        Http::assertSent(function ($request) {
            $query = (string) ($request->data()['q'] ?? '');
            return str_contains($query, 'Indofood CBP Sukses Makmur') || str_contains($query, 'saham ICBP');
        });
    }

    public function test_google_news_rss_queries_for_primary_segment_use_issuer_specific_aliases(): void
    {
        Http::fake([
            'news.google.com/*' => Http::response('<rss><channel></channel></rss>', 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia Tbk']);
        $fetcher = new GoogleNewsRssFetcher();
        $fetcher->fetchForStock($stock, 5);

        Http::assertSent(function ($request) {
            $query = (string) ($request->data()['q'] ?? '');
            return str_contains($query, 'PT Bank Central Asia Tbk')
                || str_contains($query, 'Bank Central Asia')
                || str_contains($query, 'Bank BCA')
                || str_contains($query, 'saham BBCA');
        });
    }

    public function test_google_news_rss_normalizes_overlong_source_url(): void
    {
        $longLink = 'https://news.google.com/rss/articles/'.str_repeat('a', 280);
        $rss = <<<XML
        <rss version="2.0">
          <channel>
            <item>
              <title>ICBP dapat sorotan analis</title>
              <link>{$longLink}</link>
              <description>ICBP masuk daftar saham pilihan analis.</description>
              <pubDate>Tue, 21 Apr 2026 08:00:00 +0700</pubDate>
              <source url="https://www.example.com">Example</source>
            </item>
          </channel>
        </rss>
        XML;

        Http::fake([
            'news.google.com/*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new GoogleNewsRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertLessThanOrEqual(240, strlen((string) $articles[0]['source_url']));
        $this->assertStringStartsWith('https://news.google.com/rss/articles/', (string) $articles[0]['source_url']);
    }

    public function test_google_news_rss_prioritizes_distinct_article_days_when_limit_is_tight(): void
    {
        $rss = <<<'XML'
        <rss version="2.0">
          <channel>
            <item>
              <title>BCA umumkan agenda investor day</title>
              <link>https://example.com/bbca-1</link>
              <description>Bank Central Asia memperbarui agenda investor.</description>
              <pubDate>Tue, 21 Apr 2026 08:00:00 +0700</pubDate>
              <source url="https://example.com">Example</source>
            </item>
            <item>
              <title>BCA perluas layanan treasury</title>
              <link>https://example.com/bbca-2</link>
              <description>Bank Central Asia memperluas layanan treasury.</description>
              <pubDate>Tue, 21 Apr 2026 07:00:00 +0700</pubDate>
              <source url="https://example.com">Example</source>
            </item>
            <item>
              <title>Saham BBCA diborong direksi saat koreksi</title>
              <link>https://example.com/bbca-3</link>
              <description>Investor mencermati pergerakan saham BBCA.</description>
              <pubDate>Mon, 20 Apr 2026 08:00:00 +0700</pubDate>
              <source url="https://example.com">Example</source>
            </item>
            <item>
              <title>Bank BCA diuji lagi, potensi cuan 50 persen</title>
              <link>https://example.com/bbca-4</link>
              <description>Bank BCA masuk pantauan analis teknikal.</description>
              <pubDate>Sun, 19 Apr 2026 08:00:00 +0700</pubDate>
              <source url="https://example.com">Example</source>
            </item>
          </channel>
        </rss>
        XML;

        Http::fake([
            'news.google.com/*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia Tbk']);
        $fetcher = new GoogleNewsRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 3);

        $this->assertCount(3, $articles);
        $dates = collect($articles)
            ->map(fn ($article) => $article['published_at']->toDateString())
            ->all();

        $this->assertSame(['2026-04-21', '2026-04-20', '2026-04-19'], $dates);
    }
}
