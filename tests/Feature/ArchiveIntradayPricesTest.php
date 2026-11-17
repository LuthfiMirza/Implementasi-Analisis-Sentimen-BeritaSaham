<?php

namespace Tests\Feature;

use App\Models\Stock;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ArchiveIntradayPricesTest extends TestCase
{
    use RefreshDatabase;

    public function test_archive_intraday_command_stores_15m_bars(): void
    {
        Stock::factory()->create([
            'code' => 'BUMI',
            'is_active' => true,
            'yahoo_symbol' => 'BUMI.JK',
        ]);

        $mockTimestamp = 1794906000; // unix timestamp

        Http::fake([
            'https://query1.finance.yahoo.com/*' => Http::response([
                'chart' => [
                    'result' => [
                        [
                            'timestamp' => [$mockTimestamp],
                            'indicators' => [
                                'quote' => [
                                    [
                                        'open' => [132.0],
                                        'high' => [135.0],
                                        'low' => [130.0],
                                        'close' => [134.0],
                                        'volume' => [1500000],
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ], 200),
        ]);

        $this->artisan('stocks:archive-intraday --days=1 --stock=BUMI --no-index')
            ->assertExitCode(0);

        $this->assertDatabaseHas('intraday_prices', [
            'stock_code' => 'BUMI',
            'interval' => '15m',
            'open' => 132.0,
            'high' => 135.0,
            'low' => 130.0,
            'close' => 134.0,
            'volume' => 1500000,
        ]);

        // Test idempotency on second run
        $this->artisan('stocks:archive-intraday --days=1 --stock=BUMI --no-index')
            ->assertExitCode(0);

        $this->assertSame(1, DB::table('intraday_prices')->where('stock_code', 'BUMI')->count());
    }
}
