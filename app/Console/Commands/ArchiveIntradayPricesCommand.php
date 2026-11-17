<?php

namespace App\Console\Commands;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Schema;

/**
 * Simpan bar intraday (15m) Yahoo Finance ke tabel intraday_prices secara idempotent (upsert).
 *
 * Dijalankan harian dengan jendela beberapa hari ke belakang, sehingga kalau sistem sempat mati
 * beberapa hari, run berikutnya otomatis menambal hari yang terlewat (selama masih < 60 hari).
 */
class ArchiveIntradayPricesCommand extends Command
{
    protected $signature = 'stocks:archive-intraday
        {--days=10 : Jendela hari kalender ke belakang (maks 60, batas Yahoo untuk 15m)}
        {--interval=15m : Interval bar Yahoo (15m/30m/60m)}
        {--stock=* : Batasi ke kode saham tertentu}
        {--no-index : Jangan ikut arsipkan IHSG (^JKSE, disimpan sebagai COMPOSITE)}';

    protected $description = 'Arsipkan bar intraday (default 15 menit) semua saham aktif + IHSG ke tabel intraday_prices';

    public function handle(): int
    {
        if (! Schema::hasTable('intraday_prices')) {
            $this->error('Tabel intraday_prices belum ada. Jalankan: php artisan migrate');

            return self::FAILURE;
        }

        $days = min(60, max(1, (int) $this->option('days')));
        $interval = (string) $this->option('interval');
        $codes = collect((array) $this->option('stock'))
            ->map(fn ($c) => strtoupper(trim((string) $c)))
            ->filter()
            ->values();

        $symbols = Stock::query()
            ->where('is_active', true)
            ->when($codes->isNotEmpty(), fn ($q) => $q->whereIn('code', $codes->all()))
            ->orderBy('code')
            ->get()
            ->mapWithKeys(fn (Stock $s) => [$s->code => trim((string) ($s->yahoo_symbol ?: $s->code.'.JK'))])
            ->all();

        if (! $this->option('no-index') && $codes->isEmpty()) {
            $symbols['COMPOSITE'] = '^JKSE';
        }

        $totalBars = 0;
        $failed = [];

        foreach (array_chunk($symbols, 20, true) as $chunk) {
            $responses = Http::pool(fn ($pool) => collect($chunk)->map(
                fn ($symbol, $code) => $pool->as($code)
                    ->withHeaders(['User-Agent' => 'Mozilla/5.0'])
                    ->timeout(15)
                    ->get('https://query1.finance.yahoo.com/v8/finance/chart/'.rawurlencode($symbol), [
                        'interval' => $interval,
                        'range' => $days.'d',
                    ])
            )->values()->all());

            foreach ($chunk as $code => $symbol) {
                $res = $responses[$code] ?? null;
                if (! $res instanceof \Illuminate\Http\Client\Response || ! $res->successful()) {
                    $failed[] = $code;

                    continue;
                }

                $rows = $this->parseBars($res->json(), $code, $interval);
                foreach (array_chunk($rows, 500) as $part) {
                    DB::table('intraday_prices')->upsert(
                        $part,
                        ['stock_code', 'interval', 'bar_time'],
                        ['open', 'high', 'low', 'close', 'volume', 'source', 'updated_at']
                    );
                }
                $totalBars += count($rows);
            }
        }

        $this->info(sprintf(
            'Arsip intraday %s selesai: %d bar dari %d simbol (jendela %d hari).%s',
            $interval,
            $totalBars,
            count($symbols) - count($failed),
            $days,
            $failed ? ' Gagal: '.implode(', ', $failed) : ''
        ));

        return self::SUCCESS;
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function parseBars(?array $json, string $code, string $interval): array
    {
        $result = $json['chart']['result'][0] ?? null;
        $timestamps = $result['timestamp'] ?? [];
        $quote = $result['indicators']['quote'][0] ?? [];
        $now = now('Asia/Jakarta')->toDateTimeString();
        $rows = [];

        foreach ($timestamps as $i => $ts) {
            $o = $quote['open'][$i] ?? null;
            $h = $quote['high'][$i] ?? null;
            $l = $quote['low'][$i] ?? null;
            $c = $quote['close'][$i] ?? null;
            if ($o === null || $h === null || $l === null || $c === null || $c <= 0) {
                continue; // bar kosong (jeda siang / suspensi)
            }

            $rows[] = [
                'stock_code' => $code,
                'interval' => $interval,
                'bar_time' => Carbon::createFromTimestamp($ts, 'Asia/Jakarta')->toDateTimeString(),
                'open' => round((float) $o, 2),
                'high' => round((float) $h, 2),
                'low' => round((float) $l, 2),
                'close' => round((float) $c, 2),
                'volume' => (int) ($quote['volume'][$i] ?? 0),
                'source' => 'yahoo_chart',
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        return $rows;
    }
}

