<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Services\Analytics\MacroRegulatorySignalService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class MacroRegulatorySignalServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_macro_regulatory_signal_returns_measurable_context_and_moderation(): void
    {
        $service = $this->app->make(MacroRegulatorySignalService::class);
        $referenceDate = Carbon::parse('2026-04-17');

        $articles = collect([
            NewsArticle::factory()->make([
                'stock_id' => null,
                'source_provider' => 'ojk_rss',
                'sentiment_label' => 'neutral',
                'final_quality_score' => 0.8,
                'published_at' => $referenceDate->copy()->subDay(),
                'title' => 'OJK perkuat pengawasan pasar modal',
            ]),
            NewsArticle::factory()->make([
                'stock_id' => null,
                'source_provider' => 'ojk_rss',
                'sentiment_label' => 'neutral',
                'final_quality_score' => 0.75,
                'published_at' => $referenceDate->copy()->subDays(2),
                'title' => 'OJK tegaskan tata kelola emiten',
            ]),
            NewsArticle::factory()->make([
                'stock_id' => 1,
                'source_provider' => 'rss_local',
                'sentiment_label' => 'positive',
                'final_quality_score' => 0.7,
                'published_at' => $referenceDate->copy()->subDays(2),
                'title' => 'Emiten mencatat kinerja positif',
            ]),
        ]);

        $signal = $service->evaluate($articles, 30, $referenceDate, true);

        $this->assertTrue($signal['enabled']);
        $this->assertTrue($signal['active']);
        $this->assertSame('regulatory_overhang', $signal['attention_regime']);
        $this->assertTrue($signal['caution_flag']);
        $this->assertGreaterThan(0, $signal['context_score']);
        $this->assertLessThan(1, $signal['confidence_multiplier']);
        $this->assertLessThan(1, $signal['score_multiplier']);
    }
}
