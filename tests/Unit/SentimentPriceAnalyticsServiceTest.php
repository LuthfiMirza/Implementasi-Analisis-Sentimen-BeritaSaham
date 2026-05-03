<?php

namespace Tests\Unit;

use App\Models\NewsSource;
use App\Services\Analytics\SentimentPriceAnalyticsService;
use Tests\TestCase;

class SentimentPriceAnalyticsServiceTest extends TestCase
{
    public function test_sentiment_price_analytics_returns_required_metrics(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 40);
        $this->seedArticle($stock);

        $result = (new SentimentPriceAnalyticsService())->analyze($stock, $stock->prices, $stock->newsArticles, 30);

        // These metrics drive charting and DSS calculations.
        foreach (['daily_return', 'cumulative_return', 'volatility'] as $key) {
            $this->assertArrayHasKey($key, $result);
        }
        $this->assertArrayHasKey('correlation_same_day', $result);
        $this->assertArrayHasKey('lag_h1', $result);
        $this->assertArrayHasKey('lag_h3', $result);
        $this->assertArrayHasKey('lag_h7', $result);
    }

    public function test_weighted_sentiment_is_higher_than_average_when_high_quality_articles_dominate(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 40);
        $premium = NewsSource::factory()->create(['type' => 'ojk_rss']);

        $this->seedArticle($stock, [
            'news_source_id' => $premium->id,
            'title' => 'BBCA laba bersih naik dan saham menguat',
            'sentiment_score' => 0.9,
            'source_weight' => 1.2,
            'relevance_score' => 1.0,
        ]);
        $this->seedArticle($stock, [
            'title' => 'Berita pasar netral',
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'source_weight' => 0.5,
            'relevance_score' => 0.4,
        ]);

        $result = (new SentimentPriceAnalyticsService())->analyze($stock, $stock->prices, $stock->newsArticles()->with('source')->get(), 30);

        // Quality/source weighting should lift stronger trusted sentiment above raw average.
        $this->assertGreaterThan($result['average_sentiment'], $result['weighted_sentiment']);
    }

    public function test_analytics_with_no_news_data_returns_neutral_gracefully(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 10);

        $result = (new SentimentPriceAnalyticsService())->analyze($stock, $stock->prices, collect(), 30);

        // Empty datasets must not cause division-by-zero in dashboard loads.
        $this->assertSame(0.0, $result['average_sentiment']);
        $this->assertSame(0.0, $result['weighted_sentiment']);
        $this->assertSame(0, $result['news_volume']);
    }
}
