<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\StockKeywordMapper;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class StockKeywordMapperExclusionTest extends TestCase
{
    use RefreshDatabase;

    public function test_global_exclusions_are_applied(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $mapper = new StockKeywordMapper();

        $exclusions = $mapper->exclusionKeywords($stock);

        $this->assertContains('promo', $exclusions);
        $this->assertContains('diskon', $exclusions);
    }

    public function test_unvr_and_icbp_aliases_are_expanded_but_stay_issuer_specific(): void
    {
        $mapper = new StockKeywordMapper();
        $unvr = Stock::factory()->create(['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk']);
        $icbp = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);

        $unvrKeywords = $mapper->keywords($unvr);
        $icbpKeywords = $mapper->keywords($icbp);
        $unvrSearchAliases = $mapper->searchAliases($unvr, 4);
        $icbpSearchAliases = $mapper->searchAliases($icbp, 4);

        $this->assertContains('PT Unilever Indonesia Tbk', $unvrKeywords);
        $this->assertContains('saham UNVR', $unvrKeywords);
        $this->assertContains('PT Indofood CBP Sukses Makmur Tbk', $icbpKeywords);
        $this->assertContains('saham ICBP', $icbpKeywords);
        $this->assertNotContains('Lifebuoy', $unvrKeywords);
        $this->assertNotContains('Indomie', $icbpKeywords);
        $this->assertContains($unvrSearchAliases[0], ['Unilever Indonesia', 'PT Unilever Indonesia Tbk', 'PT Unilever Indonesia']);
        $this->assertContains($icbpSearchAliases[0], ['Indofood CBP Sukses Makmur', 'PT Indofood CBP Sukses Makmur Tbk', 'PT Indofood CBP Sukses Makmur']);
    }

    public function test_official_primary_segment_aliases_stay_issuer_specific_for_search_queries(): void
    {
        $mapper = new StockKeywordMapper();

        $bbca = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia Tbk']);
        $bmri = Stock::factory()->create(['code' => 'BMRI', 'company_name' => 'Bank Mandiri Persero Tbk']);
        $goto = Stock::factory()->create(['code' => 'GOTO', 'company_name' => 'GoTo Gojek Tokopedia Tbk']);
        $indf = Stock::factory()->create(['code' => 'INDF', 'company_name' => 'Indofood Sukses Makmur Tbk']);

        $bbcaQueries = $mapper->exactSearchQueries($bbca, 5);
        $bmriQueries = $mapper->exactSearchQueries($bmri, 5);
        $gotoQueries = $mapper->exactSearchQueries($goto, 5);
        $indfQueries = $mapper->exactSearchQueries($indf, 5);

        $this->assertContains('PT Bank Central Asia Tbk', $mapper->keywords($bbca));
        $this->assertContains('Bank BCA', $mapper->keywords($bbca));
        $this->assertContains('Bank BCA', $bbcaQueries);
        $this->assertContains('saham BBCA', $bbcaQueries);
        $this->assertNotContains('BCA Digital', $mapper->keywords($bbca));
        $this->assertNotContains('BCA Finance', $mapper->keywords($bbca));

        $this->assertContains('PT Bank Mandiri Persero Tbk', $mapper->keywords($bmri));
        $this->assertContains('saham BMRI', $bmriQueries);
        $this->assertNotContains('Mandiri', $mapper->keywords($bmri));

        $this->assertContains('PT GoTo Gojek Tokopedia Tbk', $mapper->keywords($goto));
        $this->assertContains('saham GOTO', $gotoQueries);
        $this->assertNotContains('Gojek', $mapper->keywords($goto));
        $this->assertNotContains('Tokopedia', $mapper->keywords($goto));

        $this->assertContains('PT Indofood Sukses Makmur Tbk', $mapper->keywords($indf));
        $this->assertContains('saham INDF', $indfQueries);
    }
}
