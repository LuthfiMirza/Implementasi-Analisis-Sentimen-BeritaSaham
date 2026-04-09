<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AnalyticsPageTest extends TestCase
{
    use RefreshDatabase;

    public function test_analytics_page_loads_with_data(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia', 'is_active' => true]);

        // harga minimal 5 hari
        for ($i = 0; $i < 5; $i++) {
            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::now()->subDays(5 - $i),
                'close' => 1000 + ($i * 5),
                'interval_type' => '1d',
            ]);
        }

        // berita
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'Telkom optimistis laba tumbuh',
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.4,
            'sentiment_confidence' => 0.8,
            'sentiment_method' => 'rule_based',
            'published_at' => Carbon::now()->subDay(),
        ]);

        $response = $this->actingAs($user)->get('/analytics?code=TLKM&period=7');

        $response->assertStatus(200);
        $response->assertSeeText('Analytics');
        $response->assertSee('Model Pendukung Keputusan');
        $response->assertSeeText('Korelasi & Event Study');
        $response->assertSee('Prediksi');
    }
}
