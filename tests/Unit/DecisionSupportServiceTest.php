<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\NewsArticle;
use App\Services\Analytics\DecisionSupportService;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Tests\TestCase;

class DecisionSupportServiceTest extends TestCase
{
    public function test_bullish_support_status_when_scores_strong(): void
    {
        $service = new DecisionSupportService();
        $stock = new Stock(['code' => 'ABC']);

        $prices = new Collection();
        $base = 100;
        for ($i = 0; $i < 20; $i++) {
            $prices->push(new StockPrice([
                'price_date' => Carbon::parse('2024-01-01')->addDays($i),
                'close' => $base + ($i * 1.5),
            ]));
        }

        $analytics = [
            'average_sentiment' => 0.3,
            'weighted_sentiment' => 0.35,
            'sentiment_dominance' => 'positive',
            'news_volume' => 10,
            'cumulative_return' => 8,
            'price_trend' => 'naik',
            'volatility' => 2,
            'same_day_correlation' => 0.3,
            'lag_correlations' => ['h1' => 0.2],
        ];

        $result = $service->analyze($stock, $prices, new Collection(), $analytics);

        $this->assertContains($result['status'], ['Bullish Support', 'Wait and See']);
        $this->assertGreaterThan(0, $result['final_score']);
    }

    public function test_warning_status_when_signal_negative(): void
    {
        $service = new DecisionSupportService();
        $stock = new Stock(['code' => 'XYZ']);

        $prices = new Collection();
        $base = 100;
        for ($i = 0; $i < 15; $i++) {
            $prices->push(new StockPrice([
                'price_date' => Carbon::parse('2024-02-01')->addDays($i),
                'close' => $base - ($i * 1.2),
            ]));
        }

        $analytics = [
            'average_sentiment' => -0.4,
            'weighted_sentiment' => -0.45,
            'sentiment_dominance' => 'negative',
            'news_volume' => 6,
            'cumulative_return' => -7,
            'price_trend' => 'turun',
            'volatility' => 3,
            'same_day_correlation' => -0.2,
            'lag_correlations' => ['h1' => -0.25],
        ];

        $result = $service->analyze($stock, $prices, new Collection(), $analytics);

        $this->assertSame('Warning', $result['status']);
        $this->assertNotSame('Tinggi', $result['confidence']);
    }

    public function test_empty_analytics_array_recomputes_metrics(): void
    {
        $service = new DecisionSupportService();
        $stock = new Stock(['code' => 'ABC', 'company_name' => 'ABC Corp']);

        $prices = new Collection();
        for ($i = 0; $i < 20; $i++) {
            $prices->push(new StockPrice([
                'price_date' => Carbon::parse('2024-03-01')->addDays($i),
                'close' => 100 + ($i * 1.0),
            ]));
        }

        $articles = new Collection([
            new NewsArticle([
                'published_at' => Carbon::parse('2024-03-18'),
                'sentiment_label' => 'positive',
                'sentiment_score' => 0.5,
                'title' => 'ABC cetak laba',
            ]),
        ]);

        $result = $service->analyze($stock, $prices, $articles, []);

        $this->assertGreaterThan(0, $result['sentiment_average']);
        $this->assertGreaterThan(0, $result['news_volume']);
        $this->assertSame('2024-03-20', $result['prediction_features']['reference_date']);
    }
}
