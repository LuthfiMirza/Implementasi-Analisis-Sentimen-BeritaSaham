<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Services\MarketData\IdxMarketSummaryService;
use Illuminate\Support\Carbon;
use Tests\TestCase;

class MarketMacroNewsAlertTest extends TestCase
{
    public function test_macro_news_alert_flags_rate_and_rupiah_headlines(): void
    {
        NewsArticle::factory()->create([
            'stock_id' => null,
            'title' => 'The Fed naikkan bunga, rupiah melemah dan IHSG terkoreksi',
            'summary' => 'Investor asing risk-off di emerging market, bursa Asia melemah.',
            'published_at' => Carbon::parse('2026-09-18 09:00:00'),
            'sentiment_label' => 'negative',
            'sentiment_score' => -0.8,
        ]);

        $alerts = app(IdxMarketSummaryService::class)->macroNewsAlerts('2026-09-18');

        $this->assertCount(1, $alerts);
        $this->assertSame('MARKET', $alerts[0]['stock_code']);
        $this->assertSame('high', $alerts[0]['severity']);
        $this->assertContains('Suku bunga AS / The Fed', $alerts[0]['reasons']);
        $this->assertContains('Dolar kuat / rupiah lemah', $alerts[0]['reasons']);
        $this->assertContains('Bursa Asia / regional lemah', $alerts[0]['reasons']);
        $this->assertContains('IHSG melemah', $alerts[0]['reasons']);
        $this->assertContains('Asing jual / risk-off', $alerts[0]['reasons']);
    }

    public function test_macro_news_alert_ignores_plain_bank_headline(): void
    {
        $stock = $this->seedStock('BBCA');

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'Laba BCA tumbuh dobel digit, perbankan tetap defensif',
            'summary' => 'Kinerja bank tetap solid.',
            'published_at' => Carbon::parse('2026-09-18 09:00:00'),
            'sentiment_label' => 'neutral',
        ]);

        $alerts = app(IdxMarketSummaryService::class)->macroNewsAlerts('2026-09-18');

        $this->assertSame([], $alerts);
    }
}
