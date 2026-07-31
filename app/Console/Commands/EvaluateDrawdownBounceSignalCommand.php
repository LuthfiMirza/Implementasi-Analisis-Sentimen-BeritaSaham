<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase AC companion to research:detect-drawdown-bounce-signal -- fills in 5-day/10-day outcomes
 * for signals whose holding period has elapsed. See quant/drawdown_bounce_tracker/PROTOCOL.md.
 */
class EvaluateDrawdownBounceSignalCommand extends Command
{
    protected $signature = 'research:evaluate-drawdown-bounce-signal';

    protected $description = 'Fill in outcomes for drawdown-bounce signals whose horizon has elapsed (Fase AB/AC)';

    public function handle(): int
    {
        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/evaluate.py');

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
            $this->error('Gagal mengevaluasi sinyal: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }
}
