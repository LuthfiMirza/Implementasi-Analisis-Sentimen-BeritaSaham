<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\User;
use App\Models\UserWatchlist;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class WatchlistAlertTest extends TestCase
{
    use RefreshDatabase;

    public function test_dashboard_shows_negative_news_alert_for_watchlist(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'ADRO', 'company_name' => 'Adaro Energy', 'is_active' => true]);
        UserWatchlist::create(['user_id' => $user->id, 'stock_id' => $stock->id]);

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'Suspensi perdagangan ADRO',
            'sentiment_label' => 'negative',
            'sentiment_score' => -0.6,
            'sentiment_confidence' => 0.8,
            'sentiment_method' => 'rule_based',
            'published_at' => Carbon::now()->subHours(6),
        ]);
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'Tekanan margin ADRO',
            'sentiment_label' => 'negative',
            'sentiment_score' => -0.4,
            'sentiment_confidence' => 0.7,
            'sentiment_method' => 'rule_based',
            'published_at' => Carbon::now()->subHours(3),
        ]);

        $response = $this->actingAs($user)->get('/dashboard?code=ADRO');

        $response->assertStatus(200);
        $response->assertSee('Alert Watchlist');
        $response->assertSee('berita negatif');
    }
}
