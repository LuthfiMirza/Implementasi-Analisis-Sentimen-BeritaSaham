<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase AC: daily automatic detector for the "IHSG + stock crash together" bounce rule found in
 * Fase AB's historical backtest (BUMI: 27 independent episodes, consistently positive discovery
 * and holdout -- the most credible finding this project has produced so far; DEWA: only 18
 * episodes, 26% from a single month, exploratory only). See
 * quant/drawdown_bounce_tracker/PROTOCOL.md, locked before this command's first real run.
 *
 * Deliberately thin -- all detection logic lives in the Python script (fetches BUMI/DEWA/IHSG
 * directly from yfinance, no DB dependency), matching the pattern used by
 * research:collect-foreign-flow and prediction:refresh-price-history.
 */
class DetectDrawdownBounceSignalCommand extends Command
{
    protected $signature = 'research:detect-drawdown-bounce-signal';

    protected $description = 'Detect new IHSG+stock drawdown-bounce signals for BUMI/DEWA (Fase AB/AC, prospective tracker)';

    public function handle(): int
    {
        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/detect_signal.py');

        if (! is_file($script)) {
            $this->error("Script tidak ditemukan: {$script}");

            return self::FAILURE;
        }

        $result = Process::timeout(60)->run([$python, $script]);

        foreach (explode("\n", trim($result->output())) as $line) {
            if ($line !== '') {
                $this->line($line);
            }
        }

        if (! $result->successful()) {
            $this->error('Gagal mendeteksi sinyal: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }
}
