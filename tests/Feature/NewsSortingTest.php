<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NewsSortingTest extends TestCase
{
    use RefreshDatabase;

    public function test_news_sorted_by_quality_then_published_when_quality_sort_requested(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBRI']);

        $low = NewsArticle::factory()->for($stock)->create([
            'title' => 'Low quality sample',
            'final_quality_score' => 0.3,
            'published_at' => now(),
        ]);

        $high = NewsArticle::factory()->for($stock)->create([
            'title' => 'High quality sample',
            'final_quality_score' => 0.8,
            'published_at' => now()->subDay(),
        ]);

        $response = $this->actingAs($user)->get('/news?sort=quality');
        $response->assertStatus(200);

        $content = $response->getContent();
        $firstPos = strpos($content, 'High quality sample');
        $secondPos = strpos($content, 'Low quality sample');

        $this->assertNotFalse($firstPos);
        $this->assertNotFalse($secondPos);
        $this->assertTrue($firstPos < $secondPos, 'High quality article should appear before low quality when sort=quality is requested');
    }

    public function test_news_defaults_to_latest_first_when_no_sort_requested(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBRI']);

        $older = NewsArticle::factory()->for($stock)->create([
            'title' => 'Older high quality sample',
            'final_quality_score' => 0.9,
            'published_at' => now()->subDay(),
        ]);

        $newer = NewsArticle::factory()->for($stock)->create([
            'title' => 'Newer low quality sample',
            'final_quality_score' => 0.2,
            'published_at' => now(),
        ]);

        $response = $this->actingAs($user)->get('/news');
        $response->assertStatus(200);

        $content = $response->getContent();
        $firstPos = strpos($content, 'Newer low quality sample');
        $secondPos = strpos($content, 'Older high quality sample');

        $this->assertNotFalse($firstPos);
        $this->assertNotFalse($secondPos);
        $this->assertTrue($firstPos < $secondPos, 'Newest article should appear first by default, even if lower quality');
    }
}
