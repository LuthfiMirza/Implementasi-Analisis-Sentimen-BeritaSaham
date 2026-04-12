<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class DashboardNewsPanelTest extends TestCase
{
    use RefreshDatabase;

    public function test_dashboard_news_panel_prioritizes_quality(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'TLKM']);

        $low = NewsArticle::factory()->for($stock)->create([
            'title' => 'Low quality item',
            'final_quality_score' => 0.3,
            'published_at' => now(),
        ]);

        $high = NewsArticle::factory()->for($stock)->create([
            'title' => 'High quality item',
            'final_quality_score' => 0.9,
            'published_at' => now()->subHour(),
        ]);

        $response = $this->actingAs($user)->get('/dashboard?code=TLKM');
        $response->assertStatus(200);

        $news = $response->viewData('news');
        $this->assertNotNull($news);
        $this->assertEquals('High quality item', $news->first()->title);
    }
}
