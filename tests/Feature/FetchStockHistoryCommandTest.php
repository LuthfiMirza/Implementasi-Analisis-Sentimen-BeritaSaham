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

    public function test_command_rebuild_mode_replaces_legacy_daily_interval_with_clean_validated_series(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'yahoo_symbol' => 'BBCA.JK',
            'is_active' => true,
        ]);

        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => '2020-02-29',
            'interval_type' => '1d',
            'open' => 5000,
            'high' => 5200,
            'low' => 4900,
            'close' => 5100,
            'volume' => 1000,
            'source' => null,
        ]);

        $first = Carbon::create(2025, 10, 1, 9, 0, 0, 'Asia/Jakarta')->utc()->timestamp;
        $second = Carbon::create(2025, 10, 2, 9, 0, 0, 'Asia/Jakarta')->utc()->timestamp;

        Http::fake([
            '*' => Http::response([
                'chart' => [
                    'result' => [[
                        'meta' => ['exchangeTimezoneName' => 'Asia/Jakarta'],
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

        $this->artisan('stocks:fetch-history', [
            '--days' => 36500,
            '--stock' => ['BBCA'],
            '--rebuild-daily-series' => true,
        ])->assertExitCode(0);

        $dates = StockPrice::where('stock_id', $stock->id)
            ->where('interval_type', '1d')
            ->orderBy('price_date')
            ->pluck('price_date')
            ->map(fn ($date) => Carbon::parse($date)->toDateString())
            ->all();

        $this->assertSame(['2025-10-01', '2025-10-02'], $dates);
        $this->assertSame(
            ['yahoo_daily_rebuild_raw', 'yahoo_daily_rebuild_raw'],
            StockPrice::where('stock_id', $stock->id)->orderBy('price_date')->pluck('source')->all()
        );
    }

    public function test_command_skips_write_when_fetched_series_contains_weekend_rows(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBRI',
            'is_active' => true,
        ]);

        $sunday = Carbon::create(2025, 11, 2, 9, 0, 0, 'Asia/Jakarta')->utc()->timestamp;

        Http::fake([
            '*' => Http::response([
                'chart' => [
                    'result' => [[
                        'meta' => ['exchangeTimezoneName' => 'Asia/Jakarta'],
                        'timestamp' => [$sunday],
                        'indicators' => [
                            'quote' => [[
                                'open' => [100.0],
                                'high' => [101.0],
                                'low' => [99.0],
                                'close' => [100.0],
                                'volume' => [1000000],
                            ]],
                        ],
                    ]],
                ],
            ], 200),
        ]);

        $this->artisan('stocks:fetch-history', [
            '--days' => 36500,
            '--stock' => ['BBRI'],
            '--rebuild-daily-series' => true,
        ])->assertExitCode(0);

        $this->assertSame(0, StockPrice::where('stock_id', $stock->id)->count());
    }
}
