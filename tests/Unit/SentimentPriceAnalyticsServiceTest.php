<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Tests\TestCase;

class SentimentPriceAnalyticsServiceTest extends TestCase
{
    public function test_lag_correlation_and_metrics_generated(): void
    {
        $service = new SentimentPriceAnalyticsService();
        $stock = new Stock(['code' => 'ABC', 'company_name' => 'ABC Corp']);

        $prices = new Collection([
            new StockPrice(['price_date' => Carbon::parse('2024-01-01'), 'close' => 100]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-02'), 'close' => 102]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-03'), 'close' => 104]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-04'), 'close' => 103]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-05'), 'close' => 105]),
        ]);

        $articles = new Collection([
            new NewsArticle(['sentiment_score' => 0.2, 'sentiment_label' => 'positive', 'published_at' => Carbon::parse('2024-01-01'), 'title' => 'ABC optimistis']),
            new NewsArticle(['sentiment_score' => 0.4, 'sentiment_label' => 'positive', 'published_at' => Carbon::parse('2024-01-02'), 'title' => 'ABC naik']),
            new NewsArticle(['sentiment_score' => -0.3, 'sentiment_label' => 'negative', 'published_at' => Carbon::parse('2024-01-03'), 'title' => 'ABC waspada']),
        ]);

        $result = $service->analyze($stock, $prices, $articles, 7);

        $this->assertArrayHasKey('lag_correlations', $result);
        $this->assertNotNull($result['lag_correlations']['h1']);
        $this->assertArrayHasKey('event_study', $result);
        $this->assertArrayHasKey('average_sentiment', $result);
    }

    public function test_python_unavailable_articles_are_excluded_from_sentiment_metrics(): void
    {
        $service = new SentimentPriceAnalyticsService();
        $stock = new Stock(['code' => 'ABC', 'company_name' => 'ABC Corp']);

        $prices = new Collection([
            new StockPrice(['price_date' => Carbon::parse('2024-01-01'), 'close' => 100]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-02'), 'close' => 102]),
            new StockPrice(['price_date' => Carbon::parse('2024-01-03'), 'close' => 101]),
        ]);

        $articles = new Collection([
            new NewsArticle([
                'sentiment_score' => 0.6,
                'sentiment_label' => 'positive',
                'sentiment_method' => 'python',
                'published_at' => Carbon::parse('2024-01-01'),
                'title' => 'ABC optimistis',
                'final_quality_score' => 0.8,
            ]),
            new NewsArticle([
                'sentiment_score' => 0.0,
                'sentiment_label' => 'neutral',
                'sentiment_method' => 'python_unavailable',
                'published_at' => Carbon::parse('2024-01-02'),
                'title' => 'ABC unavailable',
                'final_quality_score' => 0.8,
            ]),
        ]);

        $result = $service->analyze($stock, $prices, $articles, 7, Carbon::parse('2024-01-03'));

        $this->assertSame(1, $result['news_volume']);
        $this->assertSame(1, $result['sentiment_available_count']);
        $this->assertSame(1, $result['sentiment_unavailable_count']);
        $this->assertSame(1, $result['counts']['positive']);
        $this->assertSame(0, $result['counts']['neutral']);
        $this->assertEquals(0.6, $result['average_sentiment']);
        $this->assertEquals(0.6, $result['weighted_sentiment']);
    }
}
