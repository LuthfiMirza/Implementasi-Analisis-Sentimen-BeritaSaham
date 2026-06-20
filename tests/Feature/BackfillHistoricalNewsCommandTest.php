<?php

namespace Tests\Feature;

use App\Models\Stock;
use Illuminate\Http\Client\Request;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class BackfillHistoricalNewsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_dry_run_estimates_requests_without_http_calls(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'is_active' => true]);
        Http::preventStrayRequests();

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-11-15',
            '--ticker' => ['BBCA'],
            '--source' => ['gdelt', 'newsapi'],
            '--dry-run' => true,
        ])->expectsOutputToContain('Historical news backfill DRY-RUN')
            ->expectsOutputToContain('Subtotal gdelt: 2 request')
            ->expectsOutputToContain('Subtotal newsapi: 2 request')
            ->expectsOutputToContain('Estimated total requests: 4')
            ->assertSuccessful();

        Http::assertNothingSent();
    }

    public function test_gdelt_uses_minimum_effective_delay_even_when_lower_delay_requested(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'is_active' => true]);
        Http::preventStrayRequests();

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-10-31',
            '--ticker' => ['BBCA'],
            '--source' => ['gdelt', 'google_news_rss'],
            '--delay' => 2,
            '--dry-run' => true,
        ])->expectsOutputToContain('Effective delay gdelt: 6s')
            ->expectsOutputToContain('Effective delay google_news_rss: 2s')
            ->assertSuccessful();

        Http::assertNothingSent();
    }

    public function test_dry_run_reports_cache_planned_and_skipped_chunks(): void
    {
        Cache::flush();
        Stock::factory()->create(['code' => 'BBCA', 'is_active' => true]);
        Cache::forever('news-backfill:google_news_rss:BBCA:2025-10-01:2025-10-31', 'done');
        Http::preventStrayRequests();

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-10-31',
            '--ticker' => ['BBCA'],
            '--source' => ['gdelt', 'google_news_rss'],
            '--dry-run' => true,
        ])->expectsOutputToContain('Dry-run gdelt: planned 1, skipped_done 0')
            ->expectsOutputToContain('resume skip BBCA google_news_rss 2025-10-01..2025-10-31 (dry-run)')
            ->expectsOutputToContain('Dry-run google_news_rss: planned 0, skipped_done 1')
            ->assertSuccessful();

        Http::assertNothingSent();
    }

    public function test_live_backfill_dispatches_all_default_sources(): void
    {
        config()->set('news.gdelt.min_delay_seconds', 0);
        Cache::flush();
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        Http::fake([
            'api.gdeltproject.org/*' => Http::response([
                'articles' => [[
                    'title' => 'Saham BBCA menguat setelah kinerja Bank Central Asia solid',
                    'url' => 'https://example.com/gdelt-bbca',
                    'seendate' => '20251001120000',
                    'sourceCommonName' => 'Example GDELT',
                ]],
            ]),
            'news.google.com/*' => Http::response($this->googleRssFixture()),
            'search.bisnis.com/*' => Http::response($this->businessSearchFixture()),
            'search.katadata.co.id/*' => Http::response('<html><body></body></html>'),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>'),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>'),
            'insight.kontan.co.id/*' => Http::response('<html><body></body></html>'),
        ]);

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-10-31',
            '--ticker' => ['BBCA'],
            '--delay' => 0,
            '--limit' => 5,
        ])->expectsOutputToContain('Historical news backfill LIVE')
            ->expectsOutputToContain('Backfill result summary:')
            ->assertSuccessful();

        Http::assertSent(fn (Request $request) => str_contains($request->url(), 'api.gdeltproject.org/api/v2/doc/doc'));
        Http::assertSent(fn (Request $request) => str_contains($request->url(), 'news.google.com/rss/search'));
        Http::assertSent(fn (Request $request) => str_contains($request->url(), 'search.bisnis.com'));
    }

    public function test_failed_provider_chunk_is_not_marked_done_and_other_sources_continue(): void
    {
        config()->set('news.gdelt.min_delay_seconds', 0);
        Cache::flush();
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        Http::fake([
            'api.gdeltproject.org/*' => Http::response(['message' => 'timeout simulation'], 500),
            'news.google.com/*' => Http::response($this->emptyGoogleRssFixture()),
            'search.bisnis.com/*' => Http::response('<html><body></body></html>'),
            'search.katadata.co.id/*' => Http::response('<html><body></body></html>'),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>'),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>'),
            'insight.kontan.co.id/*' => Http::response('<html><body></body></html>'),
        ]);

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-10-31',
            '--ticker' => ['BBCA'],
            '--delay' => 0,
            '--limit' => 5,
        ])->expectsOutputToContain('failed BBCA gdelt 2025-10-01..2025-10-31; will retry on next run')
            ->expectsOutputToContain('- done_empty: 2')
            ->expectsOutputToContain('- failed_retry_next_run: 1')
            ->assertSuccessful();

        $this->assertNull(Cache::get('news-backfill:gdelt:BBCA:2025-10-01:2025-10-31'));
        $this->assertSame('done', Cache::get('news-backfill:google_news_rss:BBCA:2025-10-01:2025-10-31'));
        $this->assertSame('done', Cache::get('news-backfill:business_site_search:BBCA:2025-10-01:2025-10-31'));
    }

    public function test_successful_empty_chunk_is_marked_done_and_skipped_on_rerun(): void
    {
        Cache::flush();
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        Http::fake([
            'news.google.com/*' => Http::response($this->emptyGoogleRssFixture()),
        ]);

        $arguments = [
            '--from' => '2025-10-01',
            '--to' => '2025-10-31',
            '--ticker' => ['BBCA'],
            '--source' => ['google_news_rss'],
            '--delay' => 0,
            '--limit' => 5,
        ];

        $this->artisan('news:backfill-historical', $arguments)
            ->expectsOutputToContain('- done_empty: 1')
            ->assertSuccessful();

        $this->assertSame('done', Cache::get('news-backfill:google_news_rss:BBCA:2025-10-01:2025-10-31'));

        $this->artisan('news:backfill-historical', $arguments)
            ->expectsOutputToContain('resume skip BBCA google_news_rss 2025-10-01..2025-10-31')
            ->expectsOutputToContain('- skipped_already_done: 1')
            ->assertSuccessful();
    }

    protected function googleRssFixture(): string
    {
        return <<<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><item><title>Saham BBCA Bank Central Asia menguat</title><link>https://news.google.com/articles/example</link><source>Example</source><pubDate>Wed, 01 Oct 2025 12:00:00 +0700</pubDate><description>Berita saham BBCA Bank Central Asia positif</description></item></channel></rss>
XML;
    }

    protected function emptyGoogleRssFixture(): string
    {
        return '<?xml version="1.0" encoding="UTF-8"?><rss><channel></channel></rss>';
    }

    protected function businessSearchFixture(): string
    {
        return <<<'HTML'
<html><body><div class="result"><a href="https://market.bisnis.com/read/20251001/7/1/saham-bbca-bank-central-asia-menguat">Saham BBCA Bank Central Asia menguat tajam</a><time>1 Oktober 2025</time><p>Berita saham BBCA Bank Central Asia positif.</p></div></body></html>
HTML;
    }
}
