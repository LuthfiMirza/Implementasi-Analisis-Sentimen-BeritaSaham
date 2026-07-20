<?php

namespace App\Console\Commands;

use App\Models\Stock;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Process;

/**
 * Replaces the one-time hardcoded FundamentalStockSeeder snapshot (frozen at 2025-12-31,
 * discovered stale during a 2026-07-20 audit -- BBCA's price alone had moved -11% since
 * that snapshot, meaning the displayed PBV/PER were meaningfully wrong) with a live fetch
 * via yfinance, run on a schedule so fundamentals actually stay current.
 */
class SyncStockFundamentalsCommand extends Command
{
    protected $signature = 'stocks:sync-fundamentals {--ticker=* : Optional subset of tickers}';

    protected $description = 'Fetch live PBV/PER/ROE/DER/EPS/dividend yield via yfinance and update stocks table';

    public function handle(): int
    {
        $pythonBin = base_path('quant/.venv-fundamentals/bin/python3');
        $script = base_path('quant/fetch_fundamentals.py');

        if (! is_file($pythonBin) || ! is_file($script)) {
            $this->error('quant/.venv-fundamentals atau fetch_fundamentals.py tidak ditemukan.');
            return self::FAILURE;
        }

        $result = Process::timeout(120)->run([$pythonBin, $script]);

        if (! $result->successful()) {
            $this->error('fetch_fundamentals.py gagal: '.$result->errorOutput());
            return self::FAILURE;
        }

        $rows = json_decode($result->output(), true);
        if (! is_array($rows)) {
            $this->error('Output fetch_fundamentals.py bukan JSON valid.');
            return self::FAILURE;
        }

        $requestedTickers = collect($this->option('ticker'))->map(fn ($t) => strtoupper($t))->filter();
        $updated = 0;
        $skipped = 0;
        $today = Carbon::today()->toDateString();

        foreach ($rows as $row) {
            $code = strtoupper((string) ($row['code'] ?? ''));
            if ($code === '' || ($requestedTickers->isNotEmpty() && ! $requestedTickers->contains($code))) {
                continue;
            }

            if (isset($row['error'])) {
                $this->warn("Skip {$code}: {$row['error']}");
                $skipped++;
                continue;
            }

            $stock = Stock::where('code', $code)->first();
            if (! $stock) {
                $skipped++;
                continue;
            }

            $stock->update([
                'pbv' => $row['pbv'] ?? $stock->pbv,
                'per' => $row['per'] ?? $stock->per,
                'roe' => $row['roe'] ?? $stock->roe,
                'der' => $row['der'] ?? $stock->der,
                'eps' => $row['eps'] ?? $stock->eps,
                'book_value_per_share' => $row['book_value_per_share'] ?? $stock->book_value_per_share,
                'dividend_yield' => $row['dividend_yield'] ?? $stock->dividend_yield,
                'fundamentals_updated_at' => $today,
            ]);
            $this->line("Updated {$code}: pbv={$stock->pbv} per={$stock->per} roe={$stock->roe} der={$stock->der}");
            $updated++;
        }

        $this->info("Sync selesai: {$updated} diperbarui, {$skipped} dilewati.");

        return self::SUCCESS;
    }
}
