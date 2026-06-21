<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Tests\TestCase;

class StockPriceCanonicalTest extends TestCase
{
    public function test_canonicalize_prefers_market_sources_over_seed_and_command(): void
    {
        $stock = Stock::factory()->create(['code' => 'DEWA']);

        $seed = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-03-25 00:00:00'),
            'interval_type' => '1d',
            'close' => 47.21,
            'volume' => 2_759_773,
            'source' => 'seed',
        ]);
        $command = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-03-25 10:00:00'),
            'interval_type' => '1d',
            'close' => 395,
            'volume' => 3_872_531,
            'source' => 'command',
        ]);
        $nullSource = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-03-25 15:00:00'),
            'interval_type' => '1d',
            'close' => 460,
            'volume' => 938_460_600,
            'source' => null,
        ]);
        $yahoo = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-03-25 16:00:00'),
            'interval_type' => '1d',
            'close' => 462,
            'volume' => 950_000_000,
            'source' => 'yahoo_history_incremental',
        ]);

        $canonical = StockPrice::canonicalize(collect([$seed, $command, $nullSource, $yahoo]));

        $this->assertCount(1, $canonical);
        $this->assertSame($yahoo->id, $canonical->first()->id);
        $this->assertSame(462.0, (float) $canonical->first()->close);
    }

    public function test_canonicalize_uses_null_source_before_command_and_seed(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);

        $seed = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-04-15'),
            'interval_type' => '1d',
            'close' => 9064.44,
            'volume' => 1_762_980,
            'source' => 'seed',
        ]);
        $nullSource = StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-04-15'),
            'interval_type' => '1d',
            'close' => 6550,
            'volume' => 104_880_600,
            'source' => null,
        ]);

        $canonical = StockPrice::canonicalize(collect([$seed, $nullSource]));

        $this->assertCount(1, $canonical);
        $this->assertSame($nullSource->id, $canonical->first()->id);
        $this->assertSame(6550.0, (float) $canonical->first()->close);
    }
}
