<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class FetchStockHistoryCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_uses_extended_range_for_backfill_requests_above_ninety_days(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'is_active' => true,
        ]);

        $first = Carbon::create(2025, 10, 1, 15, 0)->timestamp;
        $second = Carbon::create(2025, 10, 2, 15, 0)->timestamp;

        Http::fake([
            '*' => Http::response([
                'chart' => [
                    'result' => [[
                        'timestamp' => [$first, $second],
                        'indicators' => [
                            'quote' => [[
                                'open' => [100.0, 101.0],
                                'high' => [102.0, 103.0],
                                'low' => [99.0, 100.0],
                                'close' => [101.0, 102.0],
                                'volume' => [1000000, 1100000],
                            ]],
                        ],
                    ]],
                ],
            ], 200),
        ]);

        $this->artisan('stocks:fetch-history', ['--days' => 180])->assertExitCode(0);

        Http::assertSent(function ($request) {
            return str_contains($request->url(), 'range=6mo')
                && str_contains($request->url(), 'interval=1d');
        });

        $this->assertSame(2, StockPrice::where('stock_id', $stock->id)->count());
    }

    public function test_command_keeps_short_daily_refresh_requests_small(): void
    {
        Stock::factory()->create([
            'code' => 'BBRI',
            'is_active' => true,
        ]);

        Http::fake([
            '*' => Http::response([
                'chart' => [
                    'result' => [[
                        'timestamp' => [],
                        'indicators' => ['quote' => [[]]],
                    ]],
                ],
            ], 200),
        ]);

        $this->artisan('stocks:fetch-history', ['--days' => 1])->assertExitCode(0);

        Http::assertSent(function ($request) {
            return str_contains($request->url(), 'range=5d');
        });
    }
}
