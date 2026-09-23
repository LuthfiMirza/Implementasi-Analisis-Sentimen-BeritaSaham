<?php

namespace App\Console\Commands;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class SyncBsjpLiveCommand extends Command
{
    protected $signature = 'trade:sync-bsjp-live {--force : Paksa update meskipun data sudah ada}';

    protected $description = 'Sinkronisasi data intraday/pre-closing real-time ke idx_daily_summaries untuk radar BSJP';

    public function handle(): int
    {
        $this->info('Memulai sinkronisasi data live untuk Radar BSJP...');
        $stocks = Stock::where('is_active', true)->get()->keyBy('code');
        $tickers = $stocks->keys()->toArray();

        if (empty($tickers)) {
            $this->warn('Tidak ada saham aktif di database.');
            return self::SUCCESS;
        }

        $chunks = array_chunk($tickers, 25);
        $totalUpserted = 0;
        $today = now('Asia/Jakarta')->toDateString();

        foreach ($chunks as $chunk) {
            $responses = Http::pool(fn ($pool) =>
                array_map(fn ($t) =>
                    $pool->as($t)->withHeaders(['User-Agent' => 'Mozilla/5.0'])->timeout(6)
                         ->get('https://query2.finance.yahoo.com/v8/finance/chart/' . $t . '.JK?interval=1d&range=5d'),
                    $chunk
                )
            );

            foreach ($responses as $ticker => $res) {
                if (! $res->successful()) {
                    continue;
                }

                $data = $res->json();
                $quotes = $data['chart']['result'][0]['indicators']['quote'][0] ?? [];
                $timestamps = $data['chart']['result'][0]['timestamp'] ?? [];

                if (count($timestamps) < 2) {
                    continue;
                }

                $stockName = $stocks[$ticker]->company_name ?? ($ticker . ' Tbk.');

                // Sync 2 hari bursa terakhir untuk memastikan rasio volume dan perubahan harga presisi
                for ($i = max(1, count($timestamps) - 2); $i < count($timestamps); $i++) {
                    $date = Carbon::createFromTimestamp($timestamps[$i], 'Asia/Jakarta')->toDateString();

                    $close = $quotes['close'][$i] ?? null;
                    $open = $quotes['open'][$i] ?? null;
                    $high = $quotes['high'][$i] ?? null;
                    $low = $quotes['low'][$i] ?? null;
                    $volume = (int) ($quotes['volume'][$i] ?? 0);

                    $prevClose = $quotes['close'][$i - 1] ?? $open;

                    if (! $close || $close <= 0) {
                        continue;
                    }

                    $change = $prevClose > 0 ? ($close - $prevClose) : 0;
                    $pctChange = $prevClose > 0 ? round(($change / $prevClose) * 100, 4) : 0;
                    $value = (float) ($close * $volume);

                    DB::table('idx_daily_summaries')->updateOrInsert(
                        [
                            'trade_date' => $date,
                            'stock_code' => $ticker,
                        ],
                        [
                            'stock_name' => $stockName,
                            'previous' => (float) $prevClose,
                            'open' => (float) ($open ?: $close),
                            'high' => (float) ($high ?: $close),
                            'low' => (float) ($low ?: $close),
                            'close' => (float) $close,
                            'change' => (float) $change,
                            'pct_change' => $pctChange,
                            'volume' => $volume,
                            'value' => $value,
                            'source' => 'yahoo_live_sync',
                            'updated_at' => now('Asia/Jakarta'),
                            'created_at' => now('Asia/Jakarta'),
                        ]
                    );

                    $totalUpserted++;
                }
            }
        }

        $this->info("Sinkronisasi selesai! {$totalUpserted} catatan harga tersimpan ke idx_daily_summaries.");
        Log::info('trade:sync-bsjp-live executed', ['records' => $totalUpserted, 'today' => $today]);

        return self::SUCCESS;
    }
}
