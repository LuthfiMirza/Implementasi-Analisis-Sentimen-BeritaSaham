<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Models\StockPrice;
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

        $this->assertSame('Bullish Support', $result['status']);
        $this->assertGreaterThan(60, $result['final_score']);
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
}
