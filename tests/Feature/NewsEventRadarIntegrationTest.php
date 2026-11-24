<?php

namespace Tests\Feature;

use App\Models\StockPrice;
use App\Models\Trade;
use App\Services\News\NewsEventClassifierService;
use App\Services\Trading\TradeChartService;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class NewsEventRadarIntegrationTest extends TestCase
{
    public function test_financial_relevance_gate_filters_ambiguous_ticker_noise(): void
    {
        $svc = app(NewsEventClassifierService::class);

        $this->assertFalse($svc->isFinanciallyRelevant('115 Nama WiFi Lucu Lengkap dengan Password yang Buat Ketawa', 'WIFI'));
        $this->assertFalse($svc->isFinanciallyRelevant('Zulhas Bidik Pengembangan Budidaya Ikan Darat di 40.000 Lokasi', 'IKAN'));
        $this->assertFalse($svc->isFinanciallyRelevant('idEA Sebut Flash Sale dan Countdown Bukan Otomatis Dark Patterns', 'IDEA'));

        $this->assertTrue($svc->isFinanciallyRelevant('Manuver Hashim Jual Saham WIFI Harga Premium Rp 4,06 Triliun', 'WIFI'));
        $this->assertTrue($svc->isFinanciallyRelevant('Rukun Raharja (RAJA) Akan Buyback Saham Rp 250 Miliar', 'RAJA'));
    }

    public function test_four_tag_event_classifier_detects_catalysts_and_risks(): void
    {
        $svc = app(NewsEventClassifierService::class);

        $this->assertSame('SUSPENSION_ALERT', $svc->classifyArticle('BEI Umumkan Suspensi Saham ABCD dan Pantauan UMA')['tag']);
        $this->assertSame('HARD_RISK', $svc->classifyArticle('Rilis Kinerja Keuangan, Ini Penyebab Laba ESSA Industries Anjlok 91%')['tag']);
        $this->assertSame('CATALYST', $svc->classifyArticle('Rukun Raharja (RAJA) Akan Buyback Saham Rp 250 Miliar')['tag']);
        $this->assertSame('PANIC_DROP', $svc->classifyArticle('IHSG Ditutup Turun, Saham BUMI Masuk Daftar Top Loser')['tag']);
    }

    public function test_summarize_batch_and_trade_chart_attach_filtered_news_events_and_markers(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('RAJA');

        // Seed 25 daily bars
        $base = Carbon::parse('2026-11-01');
        for ($i = 0; $i < 25; $i++) {
            StockPrice::create([
                'stock_id' => $stock->id,
                'price_date' => $base->copy()->addDays($i)->toDateString(),
                'open' => 420 + $i,
                'high' => 430 + $i,
                'low' => 415 + $i,
                'close' => 425 + $i,
                'volume' => 1000000,
                'source' => 'test',
                'interval_type' => '1d',
            ]);
        }

        // Seed 1 noise article + 1 real CATALYST article
        DB::table('news_articles')->insert([
            [
                'stock_id' => $stock->id,
                'title' => 'Resep Nasi Goreng Raja Rasa Paling Enak',
                'slug' => 'resep-nasi-goreng-raja-test',
                'source_url' => 'https://example.test/resep-nasi-goreng-raja',
                'sentiment_label' => 'neutral',
                'sentiment_score' => 0.0,
                'published_at' => '2026-11-18 10:00:00',
                'created_at' => now(),
                'updated_at' => now(),
            ],
            [
                'stock_id' => $stock->id,
                'title' => 'Rukun Raharja (RAJA) Akan Buyback Saham Rp 250 Miliar',
                'slug' => 'raja-buyback-250m-test',
                'source_url' => 'https://example.test/raja-buyback-250m',
                'sentiment_label' => 'neutral',
                'sentiment_score' => 0.0,
                'published_at' => '2026-11-19 15:20:00',
                'created_at' => now(),
                'updated_at' => now(),
            ],
        ]);

        $trade = Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'RAJA',
            'strategy_label' => 'gabungan',
            'status' => 'open',
            'entry_price' => 424,
            'stop_loss' => 409,
            'target_1' => 445,
            'entry_date' => '2026-11-20',
        ]);

        $chart = app(TradeChartService::class)->buildChartPayload($trade, '1d');

        $this->assertSame('CATALYST', $chart['news_summary']['badge']);
        $this->assertSame(1, $chart['news_summary']['counts']['total_relevant']);
        $this->assertSame(1, $chart['news_summary']['counts']['filtered_noise']);

        $markerTexts = array_column($chart['markers'], 'text');
        $this->assertContains('📰 CATALYST', $markerTexts);
    }

    public function test_dead_low_hard_cap_prevents_falling_knife_from_getting_grade_a_plus(): void
    {
        $grader = app(\App\Services\Trading\TradeQualityGraderService::class);

        // BRPT (Tier S) with Dead Low (0.00% wick) must be capped at Grade C (0% sizing)
        $brptDeadLow = $grader->gradeTrade('BRPT', 'gabungan', [
            'rsi_14' => 31.07,
            'lower_wick_pct' => 0.0,
            'vol_ratio_ma20' => 1.27,
        ], null, 'drawdown');

        $this->assertSame('C', $brptDeadLow['grade']);
        $this->assertLessThanOrEqual(49, $brptDeadLow['quality_score']);
        $this->assertSame(0, $brptDeadLow['recommended_sizing_pct']);
        $this->assertSame('WAIT_DAY2_FLUSH', $brptDeadLow['dss_status']);
        $this->assertTrue($brptDeadLow['snapshot']['dead_low_cap_applied']);

        // ENRG (Tier A) with ideal Skenario A Lower Wick (2.78%) keeps Grade A+
        $enrgIdeal = $grader->gradeTrade('ENRG', 'gabungan', [
            'rsi_14' => 32.98,
            'lower_wick_pct' => 2.78,
            'vol_ratio_ma20' => 0.71,
        ], null, 'drawdown');

        $this->assertSame('A+', $enrgIdeal['grade']);
        $this->assertSame(100, $enrgIdeal['recommended_sizing_pct']);
        $this->assertFalse($enrgIdeal['snapshot']['dead_low_cap_applied']);
    }
}
