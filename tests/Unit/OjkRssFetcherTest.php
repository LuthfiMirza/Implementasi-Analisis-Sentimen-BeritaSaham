<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\OjkRssFetcher;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class OjkRssFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_parses_market_relevant_ojk_rss_items(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $pubDate = Carbon::now('Asia/Jakarta')->subDay()->format('D, d M Y H:i:s O');
        $rss = <<<'XML'
        <rss version="2.0">
          <channel>
            <item>
              <title>OJK terbitkan regulasi baru pasar modal</title>
              <link>https://www.ojk.go.id/id/berita/1</link>
              <description>Kebijakan pasar modal dan emiten diperkuat melalui regulasi baru.</description>
              <pubDate>%s</pubDate>
            </item>
          </channel>
        </rss>
        XML;
        $rss = sprintf($rss, $pubDate);

        Http::fake([
            '*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $fetcher = new OjkRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertCount(1, $articles);
        $this->assertSame('ojk_rss', $articles[0]['provider']);
        $this->assertSame('macro_regulatory', $articles[0]['issuer_specificity']);
        $this->assertGreaterThanOrEqual(0.4, $articles[0]['relevance_score']);
        $this->assertGreaterThanOrEqual(0.4, $articles[0]['final_quality_score']);
    }

    public function test_deduplicates_same_feed_url_once(): void
    {
        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);
        $pubDate = Carbon::now('Asia/Jakarta')->subDay()->format('D, d M Y H:i:s O');
        $rss = <<<'XML'
        <rss version="2.0">
          <channel>
            <item>
              <title>OJK dorong keterbukaan emiten</title>
              <link>https://www.ojk.go.id/id/berita/dupe</link>
              <description>Keterbukaan emiten dan pasar modal jadi fokus pengawasan.</description>
              <pubDate>%s</pubDate>
            </item>
          </channel>
        </rss>
        XML;
        $rss = sprintf($rss, $pubDate);

        Http::fake([
            '*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        $fetcher = new OjkRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertCount(1, $articles);
        $this->assertSame('https://www.ojk.go.id/id/berita/dupe', $articles[0]['source_url']);
    }

    public function test_falls_back_to_html_listing_when_rss_is_unavailable(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $today = Carbon::now('Asia/Jakarta');
        $humanDate = $today->format('j F Y');
        $listing = <<<'HTML'
        <html>
          <body>
            <a href="/id/berita-dan-kegiatan/siaran-pers/Pages/OJK-Perkuat-Regulasi-Pasar-Modal.aspx">
              OJK Perkuat Regulasi Pasar Modal
            </a>
          </body>
        </html>
        HTML;

        $articleHtml = <<<'HTML'
        <html>
          <head>
            <title>Siaran Pers: OJK Perkuat Regulasi Pasar Modal</title>
            <meta name="description" content="Siaran Pers OJK Perkuat Regulasi Pasar Modal. Jakarta, %s." />
          </head>
          <body>Jakarta, %s. OJK memperkuat regulasi pasar modal dan emiten.</body>
        </html>
        HTML;
        $articleHtml = sprintf($articleHtml, $humanDate, $humanDate);

        Http::fake([
            'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/rss' => Http::response('not found', 404, ['Content-Type' => 'text/html']),
            'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers' => Http::response($listing, 200, ['Content-Type' => 'text/html']),
            'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers' => Http::response('<html></html>', 200, ['Content-Type' => 'text/html']),
            'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/OJK-Perkuat-Regulasi-Pasar-Modal.aspx' => Http::response($articleHtml, 200, ['Content-Type' => 'text/html']),
        ]);

        $fetcher = new OjkRssFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('ojk_rss', $articles[0]['provider']);
        $this->assertSame('html_listing', $articles[0]['raw_payload']['fallback']);
        $this->assertSame('Siaran Pers: OJK Perkuat Regulasi Pasar Modal', $articles[0]['title']);
    }

    public function test_backfill_reads_paginated_listing_with_historical_range(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $pageOne = <<<'HTML'
        <html>
          <body>
            <input type="hidden" name="__VIEWSTATE" value="state-1" />
            <input type="hidden" name="__EVENTVALIDATION" value="event-1" />
            <div class="col-lg-10">
              <div class="date">14 April 2026</div>
              <a href="/id/berita-dan-kegiatan/siaran-pers/Pages/Roadmap-Pasar-Modal.aspx" class="group-item-title">
                <strong>Siaran Pers: Roadmap Pasar Modal Berkelanjutan</strong>
              </a>
              <div class="caption">Pasar modal dan investasi berkelanjutan diperkuat oleh OJK.</div>
            </div>
            <span class="pagination">
              <span class="currentPagingButton">1</span>
              <a class="pagingButton" href="javascript:__doPostBack('ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl01$ctl01','')">2</a>
            </span>
          </body>
        </html>
        HTML;

        $pageTwo = <<<'HTML'
        <html>
          <body>
            <input type="hidden" name="__VIEWSTATE" value="state-2" />
            <input type="hidden" name="__EVENTVALIDATION" value="event-2" />
            <div class="col-lg-10">
              <div class="date">15 Maret 2026</div>
              <a href="/id/berita-dan-kegiatan/siaran-pers/Pages/Edukasi-Pasar-Modal.aspx" class="group-item-title">
                <strong>Siaran Pers: OJK Perkuat Edukasi Pasar Modal</strong>
              </a>
              <div class="caption">Literasi investor dan penguatan pasar modal terus diperluas.</div>
            </div>
            <div class="col-lg-10">
              <div class="date">10 Februari 2026</div>
              <a href="/id/berita-dan-kegiatan/siaran-pers/Pages/Integritas-Pasar-Modal.aspx" class="group-item-title">
                <strong>Siaran Pers: OJK Tegaskan Integritas Pasar Modal</strong>
              </a>
              <div class="caption">Integritas bursa, emiten, dan investor tetap menjadi prioritas.</div>
            </div>
            <span class="pagination">
              <span class="currentPagingButton">2</span>
            </span>
          </body>
        </html>
        HTML;

        Http::fake(function ($request) use ($pageOne, $pageTwo) {
            $url = $request->url();

            if ($url === 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/rss') {
                return Http::response('not found', 404, ['Content-Type' => 'text/html']);
            }

            if ($url === 'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers') {
                return $request->method() === 'POST'
                    ? Http::response($pageTwo, 200, ['Content-Type' => 'text/html'])
                    : Http::response($pageOne, 200, ['Content-Type' => 'text/html']);
            }

            return Http::response('<html></html>', 200, ['Content-Type' => 'text/html']);
        });

        $fetcher = new OjkRssFetcher();
        $articles = $fetcher->fetchForMarketInRange('2026-02-01', '2026-04-15', 3, 10);

        $this->assertCount(3, $articles);
        $this->assertSame('paginated_listing', $articles[0]['raw_payload']['fallback']);
        $this->assertFalse($articles[0]['raw_payload']['detail_hydrated']);
        $this->assertSame('2026-04-14', $articles[0]['published_at']->toDateString());
        $this->assertSame('2026-03-15', $articles[1]['published_at']->toDateString());
        $this->assertSame('2026-02-10', $articles[2]['published_at']->toDateString());
    }
}
