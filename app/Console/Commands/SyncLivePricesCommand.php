<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\MarketData\LiveMarketDataService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('stocks:sync-live {--stock=} {--all-active} {--interval=1d}')]
#[Description('Sinkronisasi harga live/snapshot untuk saham aktif')]
class SyncLivePricesCommand extends Command
{
    public function handle(LiveMarketDataService $service)
    {
        $code = $this->option('stock');
        $allActive = $this->option('all-active');
        $interval = $this->option('interval') ?? '1d';

        $stocks = $code
            ? Stock::where('code', strtoupper($code))->get()
            : ($allActive ? Stock::where('is_active', true)->get() : Stock::orderBy('code')->get());

        $success = 0;
        $failed = 0;

        foreach ($stocks as $stock) {
            try {
                $quote = $service->quote($stock);
                if (! $quote) {
                    $failed++;
                    $this->warn("{$stock->code}: tidak ada data live (fallback mungkin snapshot).");
                    continue;
                }

                StockPrice::updateOrCreate(
                    [
                        'stock_id' => $stock->id,
                        'price_date' => Carbon::now()->toDateString(),
                        'interval_type' => $interval,
                    ],
                    [
                        'open' => $quote['open'],
                        'high' => $quote['high'],
                        'low' => $quote['low'],
                        'close' => $quote['close'],
                        'volume' => $quote['volume'],
                    ]
                );
                $success++;
                $this->info("{$stock->code}: sinkron berhasil (source {$quote['source']}, live=".($quote['is_live'] ? 'yes' : 'no').")");
            } catch (\Throwable $e) {
                $failed++;
                $this->error("{$stock->code}: gagal sync - ".$e->getMessage());
                \Log::error('stocks:sync-live error', ['code' => $stock->code, 'error' => $e->getMessage()]);
            }
        }

        $this->line("Summary: sukses {$success}, gagal {$failed}, total {$stocks->count()}");

        return self::SUCCESS;
    }
}
