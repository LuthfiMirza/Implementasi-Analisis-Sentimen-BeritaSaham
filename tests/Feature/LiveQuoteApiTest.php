<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\MarketData\MarketDataProviderInterface;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\Stocks\PriceSeriesService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class LiveQuoteApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_quote_endpoint_returns_live_when_provider_available(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        config(['market.data_source' => 'live']);

        $fakeProvider = new class implements MarketDataProviderInterface {
            public function quote(\App\Models\Stock $stock): ?array
            {
                return [
                    'stock_code' => $stock->code,
                    'open' => 100,
                    'high' => 110,
                    'low' => 95,
                    'close' => 105,
                    'last' => 105,
                    'volume' => 1000,
                    'change' => 5,
                    'change_percent' => 5,
                    'source' => 'fake_live',
                    'is_live' => true,
                    'fetched_at' => now(),
                ];
            }
        };

        app()->instance(LiveMarketDataService::class, new LiveMarketDataService($fakeProvider, app(PriceSeriesService::class)));

        $response = $this->getJson('/api/stocks/BBCA/quote');
        $response->assertStatus(200)
            ->assertJsonFragment(['is_live' => true, 'source' => 'fake_live']);
    }

    public function test_quote_endpoint_falls_back_to_snapshot_when_live_missing(): void
    {
        $stock = Stock::factory()->create(['code' => 'TLKM']);
        config(['market.data_source' => 'live']);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::today()->toDateString(),
            'interval_type' => '1d',
            'open' => 10,
            'high' => 12,
            'low' => 9,
            'close' => 11,
            'volume' => 500,
        ]);

        $nullProvider = new class implements MarketDataProviderInterface {
            public function quote(\App\Models\Stock $stock): ?array
            {
                return null;
            }
        };

        app()->instance(LiveMarketDataService::class, new LiveMarketDataService($nullProvider, app(PriceSeriesService::class)));

        $response = $this->getJson('/api/stocks/TLKM/quote');
        $response->assertStatus(200)
            ->assertJsonFragment(['is_live' => false, 'source' => 'backend_snapshot'])
            ->assertJsonFragment(['last' => 11]);
    }
}
