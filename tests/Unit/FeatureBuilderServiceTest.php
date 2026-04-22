<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Prediction\FeatureBuilderService;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Tests\TestCase;

class FeatureBuilderServiceTest extends TestCase
{
    public function test_build_uses_reference_date_instead_of_now(): void
    {
        $service = new FeatureBuilderService();
        $stock = new Stock(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);

        $prices = new Collection([
            new StockPrice(['price_date' => Carbon::parse('2024-01-01'), 'close' => 100]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-02'), 'close' => 101]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-03'), 'close' => 102]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-04'), 'close' => 103]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-05'), 'close' => 104]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-06'), 'close' => 105]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-07'), 'close' => 106]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-08'), 'close' => 107]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-09'), 'close' => 108]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-10'), 'close' => 109]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-11'), 'close' => 110]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-12'), 'close' => 111]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-13'), 'close' => 112]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-14'), 'close' => 113]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-15'), 'close' => 114]),
        ]);

        $articles = new Collection([
            new NewsArticle([
                'published_at' => Carbon::parse('2024-01-12'),
                'sentiment_label' => 'positive',
                'sentiment_score' => 0.6,
                'sentiment_method' => 'python',
                'title' => 'BCA catat laba',
            ]),
            new NewsArticle([
                'published_at' => Carbon::parse('2026-04-10'),
                'sentiment_label' => 'negative',
                'sentiment_score' => -0.7,
                'title' => 'Berita masa depan',
            ]),
            new NewsArticle([
                'published_at' => Carbon::parse('2024-01-13'),
                'sentiment_label' => 'neutral',
                'sentiment_score' => 0.0,
                'sentiment_method' => 'python_unavailable',
                'title' => 'BCA sentiment unavailable',
            ]),
        ]);

        $features = $service->build(
            $stock,
            $prices,
            $articles,
            [],
            7,
            Carbon::parse('2024-01-15')
        );

        $this->assertSame(1, $features['news_volume']);
        $this->assertSame(1, $features['sentiment_available_count']);
        $this->assertSame(1, $features['sentiment_unavailable_count']);
        $this->assertSame(0, $features['neutral_news_count']);
        $this->assertEquals(0.6, $features['weighted_sentiment']);
        $this->assertEquals('2024-01-15', $features['reference_date']);
    }
}
