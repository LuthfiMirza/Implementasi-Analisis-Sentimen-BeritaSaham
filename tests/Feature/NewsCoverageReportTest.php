<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NewsCoverageReportTest extends TestCase
{
    use RefreshDatabase;

    public function test_coverage_report_shows_counts_and_providers(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);

        NewsArticle::factory()->for($stock)->create([
            'source_provider' => 'newsapi',
            'quality_band' => 'high',
            'final_quality_score' => 0.8,
            'sentiment_label' => 'positive',
            'published_at' => now(),
        ]);
        NewsArticle::factory()->for($stock)->create([
            'source_provider' => 'gnews',
            'quality_band' => 'low',
            'final_quality_score' => 0.3,
            'sentiment_label' => 'neutral',
            'published_at' => now()->subDay(),
        ]);

        $this->actingAs($user);
        $this->artisan('news:coverage-report', ['--stock' => 'BBCA', '--days' => 7])
            ->assertExitCode(0);
    }
}
