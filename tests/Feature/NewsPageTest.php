<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NewsPageTest extends TestCase
{
    use RefreshDatabase;

    public function test_news_page_shows_filters_and_articles(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank BCA', 'is_active' => true]);

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BCA catat laba tumbuh',
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.5,
            'sentiment_confidence' => 0.9,
            'sentiment_method' => 'rule_based',
            'published_at' => Carbon::now()->subHours(2),
        ]);

        $response = $this->actingAs($user)->get('/news?code=BBCA');

        $response->assertStatus(200);
        $response->assertSee('Berita Pasar');
        $response->assertSee('Semua Sentimen');
        $response->assertSee('Skor');
        $response->assertSee('rule_based');
    }
}
