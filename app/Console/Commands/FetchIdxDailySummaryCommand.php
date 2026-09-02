<?php

namespace App\Console\Commands;

use App\Models\IdxDailySummary;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Ingest the IDX end-of-day Stock Summary into idx_daily_summaries (one row per stock per day).
 *
 * Primary path: invoke quant/idx_market/fetch_stock_summary.py, which uses curl_cffi browser
 * impersonation to get past Cloudflare. If IDX ever blocks that, download the Stock Summary
 * JSON manually in a browser and pass it with --file=.
 *
 * PUBLIC end-of-day data. Not broker/tick data. Feeds the descriptive Market Alerts page only.
 */
class FetchIdxDailySummaryCommand extends Command
{
    protected $signature = 'idx:fetch-daily-summary
        {--date= : Trade date (YYYY-MM-DD or YYYYMMDD). Default: today (Asia/Jakarta).}
        {--backfill=0 : Also fetch this many calendar days before --date (weekends skipped).}
        {--recover : Self-heal: fetch any of the last few trading days (before today) missing from the table.}
        {--recover-days=5 : How many trading days back --recover looks.}
        {--file= : Parse a locally saved JSON file instead of scraping (manual fallback).}
        {--force : Re-fetch dates already present in the table.}';

    protected $description = 'Ingest the IDX end-of-day stock summary (volume, price, foreign flow) for the Market Alerts page';

    public function handle(): int
    {
        $file = $this->option('file');
        $baseDate = $this->resolveDate($this->option('date'));
        $backfill = max(0, (int) $this->option('backfill'));

        if ($this->option('recover')) {
            return $this->recover();
        }

        if ($file !== null) {
            if ($backfill > 0) {
                $this->warn('--backfill diabaikan saat --file dipakai (satu file = satu tanggal).');
            }

            return $this->ingestFromFile($file);
        }

        $dates = collect(range(0, $backfill))
            ->map(fn (int $offset): CarbonImmutable => $baseDate->subDays($offset))
            ->reject(fn (CarbonImmutable $d): bool => $d->isWeekend())
            ->values();

        $totalRows = 0;
        $failures = 0;

        foreach ($dates as $date) {
            $iso = $date->toDateString();

            if (! $this->option('force') && IdxDailySummary::whereDate('trade_date', $iso)->exists()) {
                $this->line("• {$iso} sudah ada, dilewati (pakai --force untuk timpa).");

                continue;
            }

            $rows = $this->scrape($date);
            if ($rows === null) {
                $failures++;

                continue;
            }

            $count = $this->upsert($iso, $rows);
            $totalRows += $count;
            $this->info("✓ {$iso}: {$count} saham disimpan.");
        }

        if ($failures > 0 && $totalRows === 0) {
            $this->error("Gagal total ({$failures} tanggal). Coba lagi nanti atau pakai --file=.");

            return self::FAILURE;
        }

        $this->info("Selesai: {$totalRows} baris, {$failures} tanggal gagal.");

        return self::SUCCESS;
    }

    /**
     * Self-healing morning run: if the Mac was asleep at 18:35 and the evening fetch never
     * happened, this fills the gap. Only looks at trading days strictly BEFORE today -- today's
     * data is the scheduled evening job's responsibility. A missing day that scrapes to 0 rows
     * (public holiday) is simply skipped; it stays "missing" but rolls out of the window in a week.
     */
    private function recover(): int
    {
        $window = max(1, (int) $this->option('recover-days'));
        $today = CarbonImmutable::now('Asia/Jakarta')->startOfDay();

        $expected = collect();
        $cursor = $today->subDay();
        while ($expected->count() < $window) {
            if (! $cursor->isWeekend()) {
                $expected->push($cursor);
            }
            $cursor = $cursor->subDay();
        }

        $missing = $expected
            ->reject(fn (CarbonImmutable $d): bool => IdxDailySummary::whereDate('trade_date', $d->toDateString())->exists())
            ->sortBy(fn (CarbonImmutable $d): int => $d->getTimestamp())
            ->values();

        if ($missing->isEmpty()) {
            $this->info("Semua {$window} hari bursa terakhir sudah lengkap, tidak perlu recover.");

            return self::SUCCESS;
        }

        $this->warn($missing->count().' hari bursa hilang: '.$missing->map->toDateString()->implode(', ').' -- mengambil.');

        $rows = 0;
        $failures = 0;
        foreach ($missing as $date) {
            $scraped = $this->scrape($date);
            if ($scraped === null) {
                $failures++;

                continue;
            }
            $count = $this->upsert($date->toDateString(), $scraped);
            $rows += $count;
            $this->info("✓ {$date->toDateString()}: {$count} saham disimpan".($count === 0 ? ' (kemungkinan libur bursa)' : '').'.');
        }

        if ($failures > 0 && $rows === 0) {
            $this->error("Recover gagal: {$failures} tanggal tidak bisa diambil. Coba lagi nanti atau pakai --file=.");

            return self::FAILURE;
        }

        $this->info("Recover selesai: {$rows} baris, {$failures} tanggal gagal.");

        return self::SUCCESS;
    }

    private function resolveDate(?string $raw): CarbonImmutable
    {
        if ($raw === null || $raw === '') {
            return CarbonImmutable::now('Asia/Jakarta')->startOfDay();
        }

        $clean = str_replace('-', '', trim($raw));

        return CarbonImmutable::createFromFormat('Ymd', $clean, 'Asia/Jakarta')->startOfDay();
    }

    /** @return array<int, array<string, mixed>>|null */
    private function scrape(CarbonImmutable $date): ?array
    {
        $python = (string) config('market_alerts.python_binary');
        $script = (string) config('market_alerts.scrape_script');

        if (! is_file($python) || ! is_file($script)) {
            $this->error("Python/script scraper tidak ditemukan: {$python} / {$script}");

            return null;
        }

        $result = Process::timeout((int) config('market_alerts.scrape_timeout', 90))
            ->run([$python, $script, '--date', $date->format('Ymd')]);

        if (! $result->successful()) {
            $this->warn("  scrape {$date->toDateString()} gagal: ".trim($result->errorOutput() ?: $result->output()));

            return null;
        }

        return $this->decodeRows($result->output(), $date->toDateString());
    }

    private function ingestFromFile(string $path): int
    {
        if (! is_file($path)) {
            $this->error("File tidak ditemukan: {$path}");

            return self::FAILURE;
        }

        $rows = $this->decodeRows((string) file_get_contents($path), null);
        if ($rows === null) {
            return self::FAILURE;
        }

        // Trust the Date field inside the payload; fall back to --date.
        $iso = $rows[0]['Date'] ?? null;
        $iso = $iso ? CarbonImmutable::parse($iso)->toDateString() : $this->resolveDate($this->option('date'))->toDateString();

        $count = $this->upsert($iso, $rows);
        $this->info("✓ {$iso}: {$count} saham disimpan dari file.");

        return self::SUCCESS;
    }

    /**
     * Accepts either the scraper's wrapper ({date,count,rows:[...]}) or a raw IDX response
     * ({data:[...]}) or a bare array of rows.
     *
     * @return array<int, array<string, mixed>>|null
     */
    private function decodeRows(string $json, ?string $context): ?array
    {
        $decoded = json_decode(trim($json), true);

        if (is_array($decoded) && isset($decoded['rows']) && is_array($decoded['rows'])) {
            return $decoded['rows'];
        }
        if (is_array($decoded) && isset($decoded['data']) && is_array($decoded['data'])) {
            return $decoded['data'];
        }
        if (is_array($decoded) && array_is_list($decoded)) {
            return $decoded;
        }

        $this->warn('  payload JSON tidak dikenali'.($context ? " ({$context})" : '').'.');

        return null;
    }

    /** @param array<int, array<string, mixed>> $rows */
    private function upsert(string $iso, array $rows): int
    {
        $now = now();
        $records = [];

        foreach ($rows as $row) {
            $code = strtoupper(trim((string) ($row['StockCode'] ?? '')));
            if ($code === '' || ! preg_match('/^[A-Z][A-Z0-9]{1,5}$/', $code)) {
                continue;
            }

            $previous = $this->num($row['Previous'] ?? null);
            $close = $this->num($row['Close'] ?? null);
            if ($close === null || $close <= 0.0) {
                continue; // no trade / suspended -- nothing to alert on
            }

            $change = $this->num($row['Change'] ?? null) ?? ($previous !== null ? $close - $previous : null);
            $foreignBuy = (int) round($this->num($row['ForeignBuy'] ?? null) ?? 0);
            $foreignSell = (int) round($this->num($row['ForeignSell'] ?? null) ?? 0);
            $foreignNet = $foreignBuy - $foreignSell;

            $records[] = [
                'trade_date' => $iso,
                'stock_code' => $code,
                'stock_name' => trim((string) ($row['StockName'] ?? '')) ?: null,
                'remarks' => trim((string) ($row['Remarks'] ?? '')) ?: null,
                'previous' => $previous,
                'open' => $this->num($row['OpenPrice'] ?? null),
                'high' => $this->num($row['High'] ?? null),
                'low' => $this->num($row['Low'] ?? null),
                'close' => $close,
                'change' => $change,
                'pct_change' => ($previous !== null && $previous > 0.0 && $change !== null)
                    ? round($change / $previous * 100, 4)
                    : null,
                'volume' => (int) round($this->num($row['Volume'] ?? null) ?? 0),
                'value' => round($this->num($row['Value'] ?? null) ?? 0, 2),
                'frequency' => (int) round($this->num($row['Frequency'] ?? null) ?? 0),
                'foreign_buy' => $foreignBuy,
                'foreign_sell' => $foreignSell,
                'foreign_net' => $foreignNet,
                'foreign_net_value' => round($foreignNet * $close, 2),
                'listed_shares' => (int) round($this->num($row['ListedShares'] ?? null) ?? 0) ?: null,
                'source' => $this->option('file') ? 'idx_manual' : 'idx_scrape',
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        foreach (array_chunk($records, 500) as $chunk) {
            IdxDailySummary::upsert(
                $chunk,
                ['trade_date', 'stock_code'],
                [
                    'stock_name', 'remarks', 'previous', 'open', 'high', 'low', 'close', 'change',
                    'pct_change', 'volume', 'value', 'frequency', 'foreign_buy', 'foreign_sell',
                    'foreign_net', 'foreign_net_value', 'listed_shares', 'source', 'updated_at',
                ]
            );
        }

        return count($records);
    }

    private function num(mixed $value): ?float
    {
        if ($value === null || $value === '' || $value === '-') {
            return null;
        }

        if (is_string($value)) {
            $value = str_replace([',', ' '], '', $value);
        }

        return is_numeric($value) ? (float) $value : null;
    }
}
