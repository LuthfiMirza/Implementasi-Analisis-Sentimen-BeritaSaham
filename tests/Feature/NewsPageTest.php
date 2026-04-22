<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use App\Services\News\NewsAggregationService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Mockery;
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

    public function test_news_page_marks_python_unavailable_as_unavailable_instead_of_neutral(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank BCA', 'is_active' => true]);

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BCA sentiment unavailable',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'sentiment_confidence' => 0.0,
            'sentiment_method' => 'python_unavailable',
            'published_at' => Carbon::now()->subHour(),
        ]);

        $response = $this->actingAs($user)->get('/news?code=BBCA');

        $response->assertStatus(200);
        $response->assertSee('Unavailable');
        $response->assertSee('python_unavailable');
        $response->assertSee('Skor: unavailable');
    }

    public function test_neutral_filter_excludes_python_unavailable_articles(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank BCA', 'is_active' => true]);

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BCA netral valid',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'sentiment_method' => 'python',
            'published_at' => Carbon::now()->subHours(2),
        ]);
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BCA unavailable',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'sentiment_method' => 'python_unavailable',
            'published_at' => Carbon::now()->subHour(),
        ]);

        $response = $this->actingAs($user)->get('/news?code=BBCA&sentiment=neutral');

        $response->assertStatus(200);
        $response->assertSee('BCA netral valid');
        $response->assertDontSee('BCA unavailable');
    }

    public function test_refresh_api_returns_unavailable_status_honestly(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank BCA', 'is_active' => true]);
        $article = NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BCA sentiment unavailable',
            'summary' => 'IndoBERT endpoint unavailable',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'sentiment_method' => 'python_unavailable',
            'sentiment_meta' => ['python_status' => 'python_http_error'],
            'published_at' => Carbon::now()->subHour(),
        ]);

        $service = Mockery::mock(NewsAggregationService::class);
        $service->shouldReceive('refreshFromProvider')->once()->andReturn(['saved' => 0, 'updated' => 0]);
        $service->shouldReceive('fetchLatestArticles')->once()->andReturn(collect([$article]));
        $this->app->instance(NewsAggregationService::class, $service);

        $response = $this->actingAs($user)->postJson('/api/news/refresh/BBCA');

        $response->assertOk()
            ->assertJsonPath('articles.0.sentiment', 'unavailable')
            ->assertJsonPath('articles.0.sentiment_status', 'unavailable')
            ->assertJsonPath('articles.0.sentiment_available', false)
            ->assertJsonPath('articles.0.score', null)
            ->assertJsonPath('articles.0.python_status', 'python_http_error');
    }
}
