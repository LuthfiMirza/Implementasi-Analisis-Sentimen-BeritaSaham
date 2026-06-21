<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('stocks:update-snapshots {--days=1}')]
#[Description('Perbarui snapshot harga saham secara sederhana untuk demo')]
class UpdateStockSnapshotsCommand extends Command
{
    /**
     * Execute the console command.
     */
    public function handle()
    {
        $days = (int) $this->option('days');
        $stocks = Stock::where('is_active', true)->get();

        foreach ($stocks as $stock) {
            $latest = StockPrice::canonicalize($stock->prices()->where('interval_type', '1d')->get())->last();
            $base = $latest?->close ?? 1000;

            for ($i = 0; $i < $days; $i++) {
                $date = Carbon::now()->subDays($i)->toDateString();
                $delta = random_int(-50, 50);
                $close = max(10, $base + $delta);
                $open = $close + random_int(-20, 20);
                $high = max($open, $close) + random_int(0, 15);
                $low = max(1, min($open, $close) - random_int(0, 15));

                StockPrice::updateOrCreate(
                    ['stock_id' => $stock->id, 'price_date' => $date, 'interval_type' => '1d'],
                    [
                        'open' => $open,
                        'high' => $high,
                        'low' => $low,
                        'close' => $close,
                        'volume' => random_int(100_000, 5_000_000),
                        'source' => 'command',
                    ]
                );
            }

            $this->info("Snapshot {$stock->code} diperbarui.");
        }
    }
}
