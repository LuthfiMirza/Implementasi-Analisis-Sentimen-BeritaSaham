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

    public function test_news_sorted_by_quality_then_published(): void
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

        $response = $this->actingAs($user)->get('/news');
        $response->assertStatus(200);

        $content = $response->getContent();
        $firstPos = strpos($content, 'High quality sample');
        $secondPos = strpos($content, 'Low quality sample');

        $this->assertNotFalse($firstPos);
        $this->assertNotFalse($secondPos);
        $this->assertTrue($firstPos < $secondPos, 'High quality article should appear before low quality');
    }
}
