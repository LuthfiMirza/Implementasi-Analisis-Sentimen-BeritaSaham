<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase AC (lanjutan): daily manual-trailing-stop ALERT for open BUMI/DEWA positions listed in
 * quant/drawdown_bounce_tracker/open_positions.json. User explicitly wants alert-only -- this
 * never places or modifies any order, it just notifies via Telegram once price pulls back >= 4%
 * from the peak since entry, so the user can decide the exact trailing stop % themselves in
 * StockBit. Deliberately thin, matching the pattern used by the other research:* commands.
 */
class CheckTrailingStopAlertCommand extends Command
{
    protected $signature = 'research:check-trailing-stop-alert';

    protected $description = 'Alert (not execute) when an open BUMI/DEWA position pulls back >= 4% from its peak since entry';

    public function handle(): int
    {
        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/check_trailing_stop.py');

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
            $this->error('Gagal cek trailing stop: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }
}
