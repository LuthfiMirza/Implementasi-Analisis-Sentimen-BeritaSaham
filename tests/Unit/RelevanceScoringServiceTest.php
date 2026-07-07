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
            'summary' => 'Saham BBCA menguat usai emiten BBCA bagikan dividen besar untuk investor',
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

    public function test_bumi_genuine_issuer_article_scores_high_end_to_end(): void
    {
        $stock = Stock::factory()->create(['code' => 'BUMI', 'company_name' => 'Bumi Resources Tbk']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Duo Investor dengan Kepemilikan Saham BUMI Terbesar',
            'summary' => 'BUMI catatkan perubahan kepemilikan saham signifikan.',
            'source_url' => 'https://example.com/bumi-1',
        ], 'rss_local');

        $this->assertSame('direct', $result['issuer_specificity']);
        $this->assertContains('BUMI', $result['direct_keyword_hits']);
        $this->assertGreaterThanOrEqual(0.35, $result['relevance_score']);
    }

    public function test_bumi_common_word_article_does_not_score_as_issuer_relevant_end_to_end(): void
    {
        $stock = Stock::factory()->create(['code' => 'BUMI', 'company_name' => 'Bumi Resources Tbk']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Bir Tawil, Wilayah Aneh di Bumi yang Tak Diakui Negara Mana Pun',
            'summary' => 'Di tengah dunia yang penuh sengketa wilayah, ada satu tempat yang justru kebalikannya.',
            'source_url' => 'https://example.com/bumi-2',
        ], 'rss_local');

        $this->assertEmpty($result['direct_keyword_hits']);
        $this->assertNotSame('direct', $result['issuer_specificity']);
        $this->assertLessThan(0.35, $result['relevance_score']);
    }

    public function test_dewa_name_substring_article_does_not_score_as_issuer_relevant_end_to_end(): void
    {
        $stock = Stock::factory()->create(['code' => 'DEWA', 'company_name' => 'Darma Henwa Tbk']);
        $scorer = new RelevanceScoringService();
        $result = $scorer->score($stock, [
            'title' => 'Menteri Keuangan Purbaya Yudhi Sadewa menyampaikan rating',
            'summary' => 'Lembaga rating Standard dan Poor memberikan peringkat triple B dengan outlook stabil.',
            'source_url' => 'https://example.com/dewa-1',
        ], 'rss_local');

        $this->assertEmpty($result['direct_keyword_hits']);
        $this->assertLessThan(0.35, $result['relevance_score']);
    }
}
