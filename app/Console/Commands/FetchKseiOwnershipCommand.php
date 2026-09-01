<?php

namespace App\Console\Commands;

use App\Models\KseiOwnership;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;

/**
 * Ingest one monthly KSEI securities-ownership snapshot (local vs foreign composition per stock)
 * into ksei_ownerships, and compute the month-over-month foreign-ownership delta.
 *
 * KSEI does not expose a documented JSON endpoint for this, so the reliable path is a manual
 * monthly download converted to CSV:
 *
 *   php artisan ksei:fetch-ownership --file=storage/app/ksei/2026-07.csv --date=2026-07-31
 *
 * Accepted CSV: a header row plus one row per stock. The parser looks for a "Code" column and
 * either explicit "Local Total" / "Foreign Total" columns or a set of "Local *" / "Foreign *"
 * sub-columns it can sum. Amounts are share counts.
 */
class FetchKseiOwnershipCommand extends Command
{
    protected $signature = 'ksei:fetch-ownership
        {--file= : Path to the KSEI monthly ownership CSV (required -- no auto endpoint).}
        {--date= : Snapshot month-end date (YYYY-MM-DD). Default: last day of previous month.}
        {--force : Overwrite an existing snapshot for that date.}';

    protected $description = 'Ingest a monthly KSEI local/foreign ownership snapshot for the Market Alerts "Kepemilikan" tab';

    public function handle(): int
    {
        $file = $this->option('file');
        if (! $file) {
            $this->error('KSEI tidak punya endpoint publik terstruktur. Unduh file bulanan dari ksei.co.id, '
                .'simpan sebagai CSV, lalu jalankan lagi dengan --file=path/ke/file.csv');

            return self::FAILURE;
        }

        if (! is_file($file)) {
            $this->error("File tidak ditemukan: {$file}");

            return self::FAILURE;
        }

        $snapshotDate = $this->option('date')
            ? CarbonImmutable::parse($this->option('date'))->toDateString()
            : CarbonImmutable::now('Asia/Jakarta')->subMonthNoOverflow()->endOfMonth()->toDateString();

        if (! $this->option('force') && KseiOwnership::whereDate('snapshot_date', $snapshotDate)->exists()) {
            $this->warn("Snapshot {$snapshotDate} sudah ada. Pakai --force untuk timpa.");

            return self::SUCCESS;
        }

        $parsed = $this->parseCsv($file);
        if ($parsed === []) {
            $this->error('Tidak ada baris valid terbaca dari CSV.');

            return self::FAILURE;
        }

        // Previous snapshot for MoM delta.
        $prevDate = KseiOwnership::where('snapshot_date', '<', $snapshotDate)->max('snapshot_date');
        $prevForeignPct = $prevDate
            ? KseiOwnership::whereDate('snapshot_date', $prevDate)->pluck('foreign_pct', 'stock_code')
            : collect();

        $now = now();
        $records = [];
        foreach ($parsed as $row) {
            $total = $row['local'] + $row['foreign'];
            if ($total <= 0) {
                continue;
            }
            $foreignPct = round($row['foreign'] / $total * 100, 4);
            $localPct = round($row['local'] / $total * 100, 4);
            $prev = $prevForeignPct[$row['code']] ?? null;

            $records[] = [
                'snapshot_date' => $snapshotDate,
                'stock_code' => $row['code'],
                'stock_name' => $row['name'],
                'total_shares' => (int) $total,
                'local_shares' => (int) $row['local'],
                'foreign_shares' => (int) $row['foreign'],
                'local_pct' => $localPct,
                'foreign_pct' => $foreignPct,
                'foreign_pct_delta' => $prev !== null ? round($foreignPct - (float) $prev, 4) : null,
                'breakdown' => $row['breakdown'] ? json_encode($row['breakdown']) : null,
                'source' => 'ksei_manual',
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        foreach (array_chunk($records, 500) as $chunk) {
            KseiOwnership::upsert(
                $chunk,
                ['snapshot_date', 'stock_code'],
                ['stock_name', 'total_shares', 'local_shares', 'foreign_shares', 'local_pct',
                    'foreign_pct', 'foreign_pct_delta', 'breakdown', 'source', 'updated_at'],
            );
        }

        $this->info("✓ {$snapshotDate}: ".count($records).' saham disimpan'
            .($prevDate ? " (delta MoM vs {$prevDate})" : ' (belum ada snapshot sebelumnya, delta kosong)').'.');

        return self::SUCCESS;
    }

    /** @return array<int, array{code:string,name:?string,local:float,foreign:float,breakdown:array}> */
    private function parseCsv(string $path): array
    {
        $handle = fopen($path, 'rb');
        if ($handle === false) {
            return [];
        }

        $header = fgetcsv($handle);
        if ($header === false) {
            fclose($handle);

            return [];
        }
        $header = array_map(fn ($h) => strtolower(trim((string) $h)), $header);

        $codeIdx = $this->findColumn($header, ['code', 'kode', 'securitycode', 'stock code']);
        $nameIdx = $this->findColumn($header, ['name', 'nama', 'securityname', 'stock name']);
        $localTotalIdx = $this->findColumn($header, ['local total', 'total local', 'local']);
        $foreignTotalIdx = $this->findColumn($header, ['foreign total', 'total foreign', 'foreign']);

        $localCols = $this->columnsPrefixed($header, 'local', $localTotalIdx);
        $foreignCols = $this->columnsPrefixed($header, 'foreign', $foreignTotalIdx);

        $rows = [];
        while (($cells = fgetcsv($handle)) !== false) {
            $code = $codeIdx !== null ? strtoupper(trim((string) ($cells[$codeIdx] ?? ''))) : '';
            if ($code === '' || ! preg_match('/^[A-Z][A-Z0-9]{1,5}$/', $code)) {
                continue;
            }

            $local = $localTotalIdx !== null
                ? $this->num($cells[$localTotalIdx] ?? null)
                : array_sum(array_map(fn ($i) => $this->num($cells[$i] ?? null), $localCols));
            $foreign = $foreignTotalIdx !== null
                ? $this->num($cells[$foreignTotalIdx] ?? null)
                : array_sum(array_map(fn ($i) => $this->num($cells[$i] ?? null), $foreignCols));

            $rows[] = [
                'code' => $code,
                'name' => $nameIdx !== null ? (trim((string) ($cells[$nameIdx] ?? '')) ?: null) : null,
                'local' => $local,
                'foreign' => $foreign,
                'breakdown' => [
                    'local' => $this->pick($header, $cells, $localCols),
                    'foreign' => $this->pick($header, $cells, $foreignCols),
                ],
            ];
        }
        fclose($handle);

        return $rows;
    }

    /** @param array<int,string> $header */
    private function findColumn(array $header, array $names): ?int
    {
        foreach ($names as $name) {
            $idx = array_search($name, $header, true);
            if ($idx !== false) {
                return (int) $idx;
            }
        }

        return null;
    }

    /**
     * All column indexes whose header starts with $prefix, excluding the explicit total column.
     *
     * @param  array<int,string>  $header
     * @return array<int,int>
     */
    private function columnsPrefixed(array $header, string $prefix, ?int $exclude): array
    {
        $out = [];
        foreach ($header as $i => $name) {
            if ($i !== $exclude && str_starts_with($name, $prefix.' ')) {
                $out[] = $i;
            }
        }

        return $out;
    }

    /**
     * @param  array<int,string>  $header
     * @param  array<int,string>  $cells
     * @param  array<int,int>  $cols
     * @return array<string,float>
     */
    private function pick(array $header, array $cells, array $cols): array
    {
        $out = [];
        foreach ($cols as $i) {
            $key = trim(str_replace(['local ', 'foreign '], '', $header[$i]));
            $out[$key] = $this->num($cells[$i] ?? null);
        }

        return $out;
    }

    private function num(mixed $value): float
    {
        if ($value === null) {
            return 0.0;
        }
        $clean = str_replace([',', ' ', '"'], '', (string) $value);

        return is_numeric($clean) ? (float) $clean : 0.0;
    }
}
