<?php

namespace Tests;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    use CreatesApplication;
    use RefreshDatabase;

    protected function user(array $attributes = []): User
    {
        return User::factory()->create(array_merge(['role' => 'user'], $attributes));
    }

    protected function admin(array $attributes = []): User
    {
        return User::factory()->admin()->create($attributes);
    }

    protected function actingAsUser(array $attributes = []): static
    {
        return $this->actingAs($this->user($attributes));
    }

    protected function actingAsAdmin(array $attributes = []): static
    {
        return $this->actingAs($this->admin($attributes));
    }

    protected function seedStock(string $code = 'BBCA', array $attributes = []): Stock
    {
        return Stock::factory()->create(array_merge([
            'code' => strtoupper($code),
            'company_name' => strtoupper($code).' Sentimena Tbk',
            'is_active' => true,
        ], $attributes));
    }

    protected function seedPriceSeries(Stock $stock, int $days = 40, float $startClose = 1000.0): void
    {
        for ($i = 0; $i < $days; $i++) {
            $close = $startClose + ($i * 10);

            StockPrice::factory()->create([
                'stock_id' => $stock->id,
                'price_date' => Carbon::parse('2026-04-01')->addDays($i),
                'open' => $close - 5,
                'high' => $close + 15,
                'low' => $close - 15,
                'close' => $close,
                'volume' => 1_000_000 + ($i * 1000),
                'interval_type' => '1d',
            ]);
        }
    }

    protected function seedArticle(Stock $stock, array $attributes = []): NewsArticle
    {
        $source = NewsSource::factory()->create(['type' => $attributes['source_provider'] ?? 'rss_local']);

        return NewsArticle::factory()->create(array_merge([
            'stock_id' => $stock->id,
            'news_source_id' => $source->id,
            'title' => "{$stock->code} laba bersih naik dan saham menguat",
            'summary' => "{$stock->code} mencatat laba bersih naik sehingga sentimen investor positif.",
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.7,
            'sentiment_confidence' => 0.8,
            'sentiment_method' => 'rule_based',
            'published_at' => now()->subDays(2),
            'final_quality_score' => 0.8,
            'relevance_score' => 0.8,
            'source_provider' => 'rss_local',
        ], $attributes));
    }
}
