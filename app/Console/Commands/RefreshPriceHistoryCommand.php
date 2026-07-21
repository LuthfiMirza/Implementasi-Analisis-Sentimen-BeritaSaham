<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Rebuilds data/stocks/{TICKER}.csv and data/IHSG.csv from yfinance -- the static price sources
 * ResearchPredictionFeatureService reads for V6A/V6B feature engineering (technical indicators +
 * market regime), decoupled from the live stock_prices DB table. Found stale at ~2026-04-22
 * during Fase N (retrain automation was safe but wasn't actually retraining on current prices)
 * because quant/rebuild_yfinance_ohlcv.py existed and worked but was never scheduled. IHSG.csv
 * matters just as much as the per-ticker files: market_regime_bullish/regime_duration are
 * required features (ExportPredictionResearchDatasetCommand::hasMissingCoreFeature), so a stale
 * IHSG.csv silently caps the usable dataset date range even after every stock ticker is fresh.
 */
class RefreshPriceHistoryCommand extends Command
{
    protected $signature = 'prediction:refresh-price-history {--ticker=* : Optional subset of stock tickers (IHSG always refreshes)}';

    protected $description = 'Rebuild data/stocks/{TICKER}.csv + data/IHSG.csv from yfinance for the 10 official tickers + BUMI/DEWA';

    /** Tickers actually consumed by prediction:retrain-production (10 official) and prediction:retrain-volatile (BUMI/DEWA). */
    protected const TICKERS = [
        'BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'GOTO', 'INDF', 'ICBP', 'ADRO', 'UNVR', 'BUMI', 'DEWA',
    ];

    public function handle(): int
    {
        $pythonBin = base_path('quant/.venv-fundamentals/bin/python3');
        $script = base_path('quant/rebuild_yfinance_ohlcv.py');

        if (! is_file($pythonBin) || ! is_file($script)) {
            $this->error('quant/.venv-fundamentals atau rebuild_yfinance_ohlcv.py tidak ditemukan.');

            return self::FAILURE;
        }

        $requestedTickers = collect($this->option('ticker'))->map(fn ($t) => strtoupper($t))->filter();
        $tickers = $requestedTickers->isNotEmpty()
            ? collect(self::TICKERS)->intersect($requestedTickers)->values()
            : collect(self::TICKERS);

        if ($tickers->isEmpty()) {
            $this->error('Tidak ada ticker valid untuk direfresh.');

            return self::FAILURE;
        }

        $stockSeries = $tickers->map(fn ($ticker) => "{$ticker}={$ticker}.JK")->all();
        [$rebuilt, $invalid] = $this->rebuildSeries($pythonBin, $script, $stockSeries, 'data/stocks');

        // IHSG powers market-regime features for every variant, regardless of --ticker scoping --
        // always refresh it so it never silently becomes the bottleneck again.
        [$ihsgRebuilt, $ihsgInvalid] = $this->rebuildSeries($pythonBin, $script, ['IHSG=^JKSE'], 'data');
        $rebuilt += $ihsgRebuilt;
        $invalid += $ihsgInvalid;

        if ($rebuilt === 0) {
            $this->error("Refresh gagal total: 0 seri berhasil, {$invalid} invalid.");

            return self::FAILURE;
        }

        $this->info("Refresh selesai: {$rebuilt} seri diperbarui, {$invalid} dilewati.");

        return self::SUCCESS;
    }

    /** @return array{0: int, 1: int} [rebuilt count, invalid count] */
    protected function rebuildSeries(string $pythonBin, string $script, array $seriesArgs, string $outputDir): array
    {
        $command = [$pythonBin, $script];
        foreach ($seriesArgs as $series) {
            $command[] = '--series';
            $command[] = $series;
        }
        $command[] = '--output-dir';
        $command[] = $outputDir;
        $command[] = '--period';
        $command[] = 'max';

        $result = Process::timeout(300)->run($command);

        $summary = json_decode($result->output(), true);
        if (! is_array($summary) || ! isset($summary['series']) || ! is_array($summary['series'])) {
            $this->error("Output rebuild_yfinance_ohlcv.py (output-dir={$outputDir}) bukan JSON valid: ".$result->errorOutput());

            return [0, count($seriesArgs)];
        }

        $rebuilt = 0;
        $invalid = 0;
        foreach ($summary['series'] as $row) {
            $name = (string) ($row['name'] ?? '?');
            $status = (string) ($row['status'] ?? 'unknown');
            if ($status === 'rebuilt') {
                $this->info("Rebuilt {$name}: {$row['rows']} rows, range={$row['date_start']}..{$row['date_end']}");
                $rebuilt++;
            } else {
                $issues = implode(',', (array) ($row['issues'] ?? []));
                $this->warn("Skip {$name}: {$status} ({$issues})");
                $invalid++;
            }
        }

        return [$rebuilt, $invalid];
    }
}
