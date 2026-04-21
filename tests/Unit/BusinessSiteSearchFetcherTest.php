<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\BusinessSiteSearchFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class BusinessSiteSearchFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_extracts_articles_from_targeted_business_search_pages(): void
    {
        Http::fake([
            'search.bisnis.com/*' => Http::response(<<<'HTML'
                <html>
                  <body>
                    <div class="result">
                      <a href="https://market.bisnis.com/read/20260421/192/000001/unilever-indonesia-catat-laba-kuartal-i">Unilever Indonesia catat laba kuartal I</a>
                      <p>UNVR menjaga margin dan kinerja penjualan domestik.</p>
                    </div>
                  </body>
                </html>
            HTML, 200),
            'search.katadata.co.id/*' => Http::response('<html><body></body></html>', 200),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk']);
        $fetcher = new BusinessSiteSearchFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('business_site_search', $articles[0]['provider']);
        $this->assertContains($articles[0]['source_name'], ['Bisnis.com Search', 'Katadata Search', 'Kontan Search']);
        $this->assertStringContainsString('Unilever Indonesia', $articles[0]['title']);
    }

    public function test_falls_back_to_issuer_tag_pages_when_search_page_is_empty(): void
    {
        Http::fake([
            'search.katadata.co.id/*' => Http::response('<html><body><div>Tidak ada hasil</div></body></html>', 200),
            'katadata.co.id/tags/*' => Http::response(<<<'HTML'
                <html>
                  <body>
                    <article class="topic-card">
                      <a href="https://katadata.co.id/finansial/korporasi/6801/icbp-jaga-margin-di-tengah-kenaikan-biaya-bahan-baku">ICBP Jaga Margin di Tengah Kenaikan Biaya Bahan Baku</a>
                      <p>Indofood CBP Sukses Makmur menyiapkan strategi harga dan efisiensi distribusi.</p>
                    </article>
                  </body>
                </html>
            HTML, 200),
            'search.bisnis.com/*' => Http::response('<html><body></body></html>', 200),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'insight.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new BusinessSiteSearchFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('business_site_search', $articles[0]['provider']);
        $this->assertSame('Katadata Search', $articles[0]['source_name']);
        $this->assertSame('https://katadata.co.id/finansial/korporasi/6801/icbp-jaga-margin-di-tengah-kenaikan-biaya-bahan-baku', $articles[0]['source_url']);
    }

    public function test_extracts_nested_result_cards_from_search_page_variations(): void
    {
        Http::fake([
            'search.bisnis.com/*' => Http::response(<<<'HTML'
                <html>
                  <body>
                    <section class="search-results">
                      <div class="news-card search-card">
                        <div class="meta">21 April 2026</div>
                        <div class="title">
                          <a href="/read/20260421/192/000003/indofood-cbp-targetkan-pertumbuhan-penjualan">Indofood CBP Targetkan Pertumbuhan Penjualan</a>
                        </div>
                        <div class="snippet">ICBP membidik kenaikan penjualan dan menjaga margin operasional.</div>
                      </div>
                    </section>
                  </body>
                </html>
            HTML, 200),
            'search.katadata.co.id/*' => Http::response('<html><body></body></html>', 200),
            'katadata.co.id/tags/*' => Http::response('<html><body></body></html>', 200),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'insight.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new BusinessSiteSearchFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertNotEmpty($articles);
        $this->assertSame('https://search.bisnis.com/read/20260421/192/000003/indofood-cbp-targetkan-pertumbuhan-penjualan', $articles[0]['source_url']);
        $this->assertStringContainsString('ICBP', (string) $articles[0]['summary']);
    }

    public function test_skips_non_issuer_search_results(): void
    {
        Http::fake([
            'search.bisnis.com/*' => Http::response(<<<'HTML'
                <html>
                  <body>
                    <div class="result">
                      <a href="https://market.bisnis.com/read/20260421/190/000002/harga-minyak-naik">Harga minyak naik</a>
                      <p>Artikel makro umum tanpa penyebutan emiten target.</p>
                    </div>
                  </body>
                </html>
            HTML, 200),
            'search.katadata.co.id/*' => Http::response('<html><body></body></html>', 200),
            'katadata.co.id/tags/*' => Http::response('<html><body></body></html>', 200),
            'search.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'english.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
            'insight.kontan.co.id/*' => Http::response('<html><body></body></html>', 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $fetcher = new BusinessSiteSearchFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertSame([], $articles);
    }

    public function test_bbca_search_queries_include_ticker_and_short_issuer_aliases(): void
    {
        Http::fake([
            '*' => Http::response('<html><body></body></html>', 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia Tbk']);
        $fetcher = new BusinessSiteSearchFetcher();
        $fetcher->fetchForStock($stock, 5);

        Http::assertSent(function ($request) {
            $url = $request->url();

            return str_contains($url, 'Bank+BCA')
                || str_contains($url, 'saham+BBCA')
                || str_contains($url, 'Bank+Central+Asia');
        });
    }
}
