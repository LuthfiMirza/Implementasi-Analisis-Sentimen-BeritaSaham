<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

class FetchStockHistoryCommand extends Command
{
    protected $signature = 'stocks:fetch-history {--days=90 : Jumlah hari historis, default 90 (3mo)}';

    protected $description = 'Fetch harga historis (OHLCV) via Yahoo Finance untuk semua saham aktif';

    public function handle(): int
    {
        $days = (int) $this->option('days');
        $range = $days >= 90 ? '3mo' : ($days >= 60 ? '2mo' : '1mo');
        $stocks = Stock::where('is_active', true)->get();

        foreach ($stocks as $stock) {
            $symbol = $stock->code.'.JK';
            $url = 'https://query1.finance.yahoo.com/v8/finance/chart/'.$symbol;
            $params = [
                'interval' => '1d',
                'range' => $range,
            ];

            try {
                $response = Http::timeout(10)->get($url, $params);
            } catch (\Throwable $e) {
                $this->error("{$stock->code}: request error {$e->getMessage()}");
                continue;
            }

            if (! $response->successful()) {
                $this->error("{$stock->code}: HTTP ".$response->status());
                continue;
            }

            $json = $response->json();
            $result = data_get($json, 'chart.result.0');
            $timestamps = data_get($result, 'timestamp', []);
            $quote = data_get($result, 'indicators.quote.0', []);

            if (! is_array($timestamps) || ! is_array($quote)) {
                $this->error("{$stock->code}: invalid payload");
                continue;
            }

            $saved = 0;
            foreach ($timestamps as $idx => $ts) {
                $date = Carbon::createFromTimestamp($ts)->toDateString();
                $open = data_get($quote, "open.$idx");
                $high = data_get($quote, "high.$idx");
                $low = data_get($quote, "low.$idx");
                $close = data_get($quote, "close.$idx");
                $vol = data_get($quote, "volume.$idx");

                if (is_null($open) || is_null($high) || is_null($low) || is_null($close) || is_null($vol)) {
                    continue;
                }

                StockPrice::updateOrCreate(
                    ['stock_id' => $stock->id, 'price_date' => $date, 'interval_type' => '1d'],
                    [
                        'open' => $open,
                        'high' => $high,
                        'low' => $low,
                        'close' => $close,
                        'volume' => (int) $vol,
                    ]
                );
                $saved++;
            }

            $this->info("{$stock->code}: fetched ".count($timestamps)." days, saved {$saved} rows");
        }

        return self::SUCCESS;
    }
}
