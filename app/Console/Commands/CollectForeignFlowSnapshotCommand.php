<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase X: appends today's top-5 net foreign buy/sell snapshot (infovesta.com) to
 * quant/foreign_flow_tracker/snapshots.jsonl. Deliberately thin -- all parsing lives in the
 * Python script (quant/foreign_flow_tracker/collect_snapshot.py); this command just invokes it
 * on a schedule and surfaces its output/exit code, matching the pattern used by
 * prediction:refresh-price-history.
 *
 * This is NOT a production model feature. The source has no history (its ?date= parameter is
 * ignored -- confirmed live-only) and only covers whichever 5 stocks top the leaderboard each
 * day, so nothing here can be walk-forward validated yet. The point of running this daily is
 * purely to accumulate a genuine history over time, the same way Fase V's signal tracker
 * accumulates Telegram signals before any conclusion is drawn.
 */
class CollectForeignFlowSnapshotCommand extends Command
{
    protected $signature = 'research:collect-foreign-flow';

    protected $description = 'Append today\'s top-5 net foreign buy/sell snapshot to the local research log (Fase X, not a production feature)';

    public function handle(): int
    {
        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/foreign_flow_tracker/collect_snapshot.py');

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
            $this->error('Gagal mengumpulkan snapshot: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }
}
