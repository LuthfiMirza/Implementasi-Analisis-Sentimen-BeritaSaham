<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\IdxDisclosureFetcher;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class IdxDisclosureFetcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_extracts_official_idx_entries_for_matching_ticker(): void
    {
        $html = <<<'HTML'
        <html>
          <body>
            <div>21 Apr 2026 17</div>
            <div>Code</div>
            <div>Description</div>
            <div>Location</div>
            <div>UNVR</div>
            <div>Pemberitahuan RUPS Tahunan PT Unilever Indonesia Tbk</div>
            <div>Grha Unilever, BSD City</div>
            <div>ICBP</div>
            <div>Tanggal DPS Dividen Tunai PT Indofood CBP Sukses Makmur Tbk</div>
            <div>Jakarta</div>
          </body>
        </html>
        HTML;

        Http::fake([
            'www.idx.id/*' => Http::response($html, 200),
        ]);

        $stock = Stock::factory()->create(['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk']);
        $fetcher = new IdxDisclosureFetcher();
        $articles = $fetcher->fetchForStock($stock, 5);

        $this->assertCount(1, $articles);
        $this->assertSame('idx_disclosure', $articles[0]['provider']);
        $this->assertSame('IDX Listed Company Calendar', $articles[0]['source_name']);
        $this->assertSame('Pemberitahuan RUPS Tahunan PT Unilever Indonesia Tbk', $articles[0]['title']);
        $this->assertTrue($articles[0]['skip_relevance_rescore']);
        $this->assertGreaterThan(0.7, $articles[0]['final_quality_score']);
    }
}
