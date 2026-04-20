<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Stocks\PriceSeriesService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class PriceSeriesServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_get_series_collapses_duplicate_trade_dates_and_prefers_non_seed_rows(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BUMI',
            'company_name' => 'Bumi Resources',
        ]);

        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 16, 0),
            'interval_type' => '1d',
            'open' => 250,
            'high' => 260,
            'low' => 245,
            'close' => 252,
            'volume' => 5000000,
            'source' => null,
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 16, 15),
            'interval_type' => '1d',
            'open' => 120,
            'high' => 130,
            'low' => 110,
            'close' => 125,
            'volume' => 150000,
            'source' => 'seed',
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 17, 0),
            'interval_type' => '1d',
            'open' => 248,
            'high' => 250,
            'low' => 240,
            'close' => 248,
            'volume' => 4000000,
            'source' => null,
        ]);

        $service = app(PriceSeriesService::class);
        $series = $service->getSeries($stock, '1d', 10);

        $this->assertCount(2, $series);
        $this->assertSame('2026-04-16', $series->first()->price_date->toDateString());
        $this->assertSame(252.0, (float) $series->first()->close);
        $this->assertSame('2026-04-17', $series->last()->price_date->toDateString());
    }

    public function test_latest_with_change_uses_normalized_daily_series(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'DEWA',
            'company_name' => 'Darma Henwa',
        ]);

        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 16, 0),
            'interval_type' => '1d',
            'open' => 535,
            'high' => 545,
            'low' => 530,
            'close' => 540,
            'volume' => 3100000,
            'source' => null,
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 17, 0),
            'interval_type' => '1d',
            'open' => 555,
            'high' => 560,
            'low' => 545,
            'close' => 550,
            'volume' => 3000000,
            'source' => null,
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 17, 15),
            'interval_type' => '1d',
            'open' => 80,
            'high' => 90,
            'low' => 70,
            'close' => 88,
            'volume' => 200000,
            'source' => 'seed',
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 4, 18, 15),
            'interval_type' => '1d',
            'open' => 79,
            'high' => 82,
            'low' => 50,
            'close' => 66,
            'volume' => 180000,
            'source' => 'seed',
        ]);

        $service = app(PriceSeriesService::class);
        $meta = $service->latestWithChange($stock, '1d');

        $this->assertSame(550.0, (float) $meta['latest']->close);
        $this->assertSame(540.0, (float) $meta['previous']->close);
        $this->assertSame(1.85, (float) $meta['change_pct']);
    }
}
