<?php

namespace Tests\Feature;

use App\Models\Stock;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class SyncStockFundamentalsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_updates_stock_fundamentals_from_python_output(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'pbv' => 1.0]);

        Process::fake([
            '*' => Process::result(output: json_encode([
                ['code' => 'BBCA', 'pbv' => 3.094, 'per' => 13.86, 'roe' => 22.97, 'der' => null, 'eps' => 470.73, 'dividend_yield' => 5.5, 'book_value_per_share' => 2108.89],
            ])),
        ]);

        $this->artisan('stocks:sync-fundamentals')->assertExitCode(0);

        $stock = Stock::where('code', 'BBCA')->first();
        $this->assertEqualsWithDelta(3.094, $stock->pbv, 0.001);
        $this->assertEqualsWithDelta(13.86, $stock->per, 0.001);
        $this->assertEqualsWithDelta(2108.89, $stock->book_value_per_share, 0.01);
        $this->assertSame(now()->toDateString(), $stock->fundamentals_updated_at->toDateString());
    }

    public function test_null_field_falls_back_to_existing_value_instead_of_wiping_it(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'der' => 5.2]);

        Process::fake([
            '*' => Process::result(output: json_encode([
                ['code' => 'BBCA', 'pbv' => 3.0, 'per' => 13.0, 'roe' => 20.0, 'der' => null, 'eps' => 400, 'dividend_yield' => 5.0, 'book_value_per_share' => 2000],
            ])),
        ]);

        $this->artisan('stocks:sync-fundamentals');

        // yfinance has no DER for banks -- must not silently wipe the previously known value.
        $this->assertSame(5.2, Stock::where('code', 'BBCA')->first()->der);
    }

    public function test_skips_ticker_reported_as_error_without_crashing(): void
    {
        Stock::factory()->create(['code' => 'GOTO', 'pbv' => 1.1]);

        Process::fake([
            '*' => Process::result(output: json_encode([
                ['code' => 'GOTO', 'error' => 'HTTPError 404'],
            ])),
        ]);

        $this->artisan('stocks:sync-fundamentals')->assertExitCode(0);

        // Untouched -- error rows are skipped, not zeroed out.
        $this->assertSame(1.1, Stock::where('code', 'GOTO')->first()->pbv);
    }

    public function test_ticker_option_filters_to_requested_subset(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'pbv' => 1.0]);
        Stock::factory()->create(['code' => 'BBRI', 'pbv' => 1.0]);

        Process::fake([
            '*' => Process::result(output: json_encode([
                ['code' => 'BBCA', 'pbv' => 3.094, 'per' => 13.86, 'roe' => 22.97, 'der' => null, 'eps' => 470.73, 'dividend_yield' => 5.5, 'book_value_per_share' => 2108.89],
                ['code' => 'BBRI', 'pbv' => 1.36, 'per' => 7.86, 'roe' => 18.14, 'der' => null, 'eps' => 389.07, 'dividend_yield' => 14.07, 'book_value_per_share' => 2246.08],
            ])),
        ]);

        $this->artisan('stocks:sync-fundamentals', ['--ticker' => ['BBCA']]);

        $this->assertEqualsWithDelta(3.094, Stock::where('code', 'BBCA')->first()->pbv, 0.001);
        $this->assertSame(1.0, Stock::where('code', 'BBRI')->first()->pbv);
    }
}
