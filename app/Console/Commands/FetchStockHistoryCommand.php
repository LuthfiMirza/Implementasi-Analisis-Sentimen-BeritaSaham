<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\Stocks\DailyPriceSeriesValidator;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;

class FetchStockHistoryCommand extends Command
{
    protected $signature = 'stocks:fetch-history
        {--days=90 : Jumlah hari historis yang diinginkan untuk backfill harga 1D}
        {--stock=* : Optional stock code(s) to target}
        {--rebuild-daily-series : Replace the full stored 1D interval with a validated daily series}';

    protected $description = 'Fetch harga historis (OHLCV) via Yahoo Finance untuk semua saham aktif';

    public function __construct(
        protected DailyPriceSeriesValidator $dailyPriceSeriesValidator
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $days = max(1, (int) $this->option('days'));
        $range = $this->resolveYahooRange($days);
        $rebuildDailySeries = (bool) $this->option('rebuild-daily-series');
        $requestedCodes = collect((array) $this->option('stock'))
            ->map(fn (mixed $code): string => strtoupper(trim((string) $code)))
            ->filter()
            ->values();

        $stocks = Stock::query()
            ->where('is_active', true)
            ->when(
                $requestedCodes->isNotEmpty(),
                fn ($query) => $query->whereIn('code', $requestedCodes->all())
            )
            ->orderBy('code')
            ->get();

        if ($stocks->isEmpty()) {
            $this->error('No active stocks matched the requested selection.');

            return self::FAILURE;
        }

        foreach ($stocks as $stock) {
            $symbol = trim((string) ($stock->yahoo_symbol ?: $stock->code.'.JK'));
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
            $timezone = (string) data_get($result, 'meta.exchangeTimezoneName', config('app.timezone', 'UTC'));

            if (! is_array($timestamps) || ! is_array($quote)) {
                $this->error("{$stock->code}: invalid payload");
                continue;
            }

            $dailyRows = [];
            foreach ($timestamps as $idx => $ts) {
                $date = Carbon::createFromTimestamp($ts, 'UTC')->setTimezone($timezone)->toDateString();
                $open = data_get($quote, "open.$idx");
                $high = data_get($quote, "high.$idx");
                $low = data_get($quote, "low.$idx");
                $close = data_get($quote, "close.$idx");
                $vol = data_get($quote, "volume.$idx");

                if (is_null($open) || is_null($high) || is_null($low) || is_null($close) || is_null($vol)) {
                    continue;
                }

                $dailyRows[] = [
                    'date' => $date,
                    'open' => (float) $open,
                    'high' => (float) $high,
                    'low' => (float) $low,
                    'close' => (float) $close,
                    'volume' => (int) $vol,
                ];
            }

            $validation = $this->dailyPriceSeriesValidator->validate($dailyRows);
            if (! $validation['valid']) {
                $this->error(
                    sprintf(
                        '%s: daily history validation failed (%s)',
                        $stock->code,
                        implode(', ', $validation['errors'])
                    )
                );

                continue;
            }

            if ($rebuildDailySeries) {
                $saved = $this->replaceDailyHistory($stock, $dailyRows);
            } else {
                $saved = $this->upsertDailyHistory($stock, $dailyRows);
            }

            $this->info("{$stock->code}: fetched ".count($dailyRows)." days, saved {$saved} rows");
        }

        return self::SUCCESS;
    }

    /**
     * @param  list<array<string, mixed>>  $dailyRows
     */
    protected function replaceDailyHistory(Stock $stock, array $dailyRows): int
    {
        return DB::transaction(function () use ($stock, $dailyRows): int {
            StockPrice::query()
                ->where('stock_id', $stock->id)
                ->where('interval_type', '1d')
                ->delete();

            $now = now();
            $payload = collect($dailyRows)
                ->map(fn (array $row): array => [
                    'stock_id' => $stock->id,
                    'price_date' => $row['date'],
                    'interval_type' => '1d',
                    'open' => $row['open'],
                    'high' => $row['high'],
                    'low' => $row['low'],
                    'close' => $row['close'],
                    'volume' => $row['volume'],
                    'source' => 'yahoo_daily_rebuild_raw',
                    'created_at' => $now,
                    'updated_at' => $now,
                ])
                ->chunk(500);

            foreach ($payload as $chunk) {
                StockPrice::insert($chunk->all());
            }

            return count($dailyRows);
        });
    }

    /**
     * @param  list<array<string, mixed>>  $dailyRows
     */
    protected function upsertDailyHistory(Stock $stock, array $dailyRows): int
    {
        $saved = 0;

        foreach ($dailyRows as $row) {
            StockPrice::updateOrCreate(
                ['stock_id' => $stock->id, 'price_date' => $row['date'], 'interval_type' => '1d'],
                [
                    'open' => $row['open'],
                    'high' => $row['high'],
                    'low' => $row['low'],
                    'close' => $row['close'],
                    'volume' => $row['volume'],
                    'source' => 'yahoo_history_incremental',
                ]
            );
            $saved++;
        }

        return $saved;
    }

    protected function resolveYahooRange(int $days): string
    {
        // Fix history-range cap so requests above 90 days can actually extend beyond the old 3mo window.
        if ($days <= 5) {
            return '5d';
        }
        if ($days <= 30) {
            return '1mo';
        }
        if ($days <= 90) {
            return '3mo';
        }
        if ($days <= 180) {
            return '6mo';
        }
        if ($days <= 365) {
            return '1y';
        }
        if ($days <= 730) {
            return '2y';
        }
        if ($days <= 1825) {
            return '5y';
        }
        if ($days <= 3650) {
            return '10y';
        }

        return 'max';
    }
}
