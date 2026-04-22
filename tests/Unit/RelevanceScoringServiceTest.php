<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\RelevanceScoringService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RelevanceScoringServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_high_relevance_when_title_matches(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Bank Central Asia umumkan dividen',
            'summary' => 'BBCA bagikan dividen besar',
            'source_url' => 'https://example.com/a',
        ], 'newsapi');

        $this->assertEquals('high', $result['relevance_band']);
        $this->assertGreaterThan(0.6, $result['relevance_score']);
    }

    public function test_low_relevance_when_no_match(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Cuaca cerah di Jakarta',
            'summary' => 'Prakiraan cuaca',
            'source_url' => 'https://example.com/b',
        ], 'gdelt');

        $this->assertEquals('low', $result['relevance_band']);
        $this->assertLessThan(0.35, $result['relevance_score']);
    }

    public function test_icbp_exact_issuer_title_is_not_penalized_by_parent_brand_overlap(): void
    {
        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Indofood CBP Targetkan Pertumbuhan Penjualan 7 Persen pada 2026',
            'summary' => 'ICBP menargetkan pertumbuhan penjualan dan menjaga margin operasional.',
            'source_url' => 'https://readers.id/industri/icbp-targetkan-pertumbuhan',
        ], 'google_news_rss');

        $this->assertSame('direct', $result['issuer_specificity']);
        $this->assertContains('Indofood CBP', $result['direct_keyword_hits']);
        $this->assertGreaterThanOrEqual(0.35, $result['relevance_score']);
    }

    public function test_icbp_film_lifestyle_article_stays_below_relevance_threshold(): void
    {
        $stock = Stock::factory()->create(['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => "Lewat 'Garuda di Dadaku', Indofood CBP Ajak Generasi Muda Berani Bermimpi dan Berkarya",
            'summary' => 'Film animasi dan kampanye kreatif untuk penonton keluarga.',
            'source_url' => 'https://nakita.grid.id/read/film-garuda-di-dadaku',
        ], 'google_news_rss');

        $this->assertLessThan(0.35, $result['relevance_score']);
        $this->assertContains('hit_exclusion:film', $result['quality_flags']);
    }
}
