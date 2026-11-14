<?php

namespace App\Console\Commands;

use App\Models\Trade;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Process;
use Throwable;

/**
 * Fase AC (lanjutan): daily trailing-stop & hard stop-loss monitor for open positions listed in
 * quant/drawdown_bounce_tracker/open_positions.json. Sends Telegram alerts and automatically
 * closes matching open Trade records in the Trade Journal when Lapis 1 (Hard Stop Loss -3.5%)
 * or Lapis 2 (Trailing Stop 2.0% from Peak) is triggered.
 */
class CheckTrailingStopAlertCommand extends Command
{
    protected $signature = 'research:check-trailing-stop-alert';

    protected $description = 'Monitor open positions for Lapis 1 (-3.5% Stop Loss) & Lapis 2 (2.0% Trailing Stop) alerts and auto-close triggered trades';

    public function handle(): int
    {
        Artisan::call('research:check-telegram-commands', ['--reconcile-only' => true]);

        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/check_trailing_stop.py');

        if (! is_file($script)) {
            $this->error("Script tidak ditemukan: {$script}");

            return self::FAILURE;
        }

        $result = Process::timeout(60)->run([$python, $script]);

        $outputLines = explode("\n", trim($result->output()));
        foreach ($outputLines as $line) {
            if ($line !== '') {
                $this->line($line);
            }
        }

        $closedCount = $this->syncAlertClosesToTradeJournal($outputLines);
        if ($closedCount > 0) {
            Artisan::call('research:check-telegram-commands', ['--reconcile-only' => true]);
        }

        if (! $result->successful()) {
            $this->error('Gagal cek trailing stop: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }

    /**
     * Auto-close open trades in MySQL Trade Journal when check_trailing_stop.py emits:
     * SYNC_ALERT_CLOSE|TICKER|PRICE|DATETIME|RESULT|STRATEGY|ENTRY_DATE
     */
    private function syncAlertClosesToTradeJournal(array $outputLines): int
    {
        $closedCount = 0;

        foreach ($outputLines as $line) {
            if (! str_starts_with($line, 'SYNC_ALERT_CLOSE|')) {
                continue;
            }

            [, $ticker, $price, $dateStr, $resultType, $strategy, $entryDate] = array_pad(explode('|', $line), 7, null);
            if (! $ticker || ! is_numeric($price)) {
                continue;
            }

            $resultType = in_array($resultType, ['stop_loss', 'trailing_stop', 'time_stop'], true)
                ? $resultType
                : 'trailing_stop';

            try {
                $query = Trade::where('ticker', $ticker)->where('status', 'open');
                $strategyLabel = $strategy ? match (strtoupper(trim($strategy))) {
                    'MOMENTUM' => 'momentum',
                    'BOTTOM_REBOUND' => 'bottom_rebound',
                    'BOTTOM_TO_TOP' => 'bottom_to_top',
                    default => 'gabungan',
                } : null;

                if ($entryDate && $strategyLabel) {
                    $matched = (clone $query)
                        ->whereDate('entry_date', $entryDate)
                        ->where('strategy_label', $strategyLabel)
                        ->get();
                } else {
                    $matched = collect();
                }

                if ($matched->isEmpty() && $entryDate) {
                    $matched = (clone $query)->whereDate('entry_date', $entryDate)->get();
                }

                if ($matched->isEmpty()) {
                    $matched = $query->orderByDesc('entry_date')->get();
                }

                if ($matched->isEmpty()) {
                    continue;
                }

                $exitDate = $dateStr ? Carbon::parse($dateStr) : Carbon::now();
                foreach ($matched as $trade) {
                    $snap = is_array($trade->indicators_snapshot) ? $trade->indicators_snapshot : [];
                    $exitPrice = (float) $price;
                    $entryPrice = (float) $trade->entry_price;
                    if ($entryPrice > 0) {
                        $snap['exit_mfe_pct'] = round(($exitPrice - $entryPrice) / $entryPrice * 100, 2);
                        $snap['exit_result_type'] = $resultType;
                        $trade->indicators_snapshot = $snap;
                    }
                    $trade->close($exitPrice, $resultType, $exitDate);
                    $closedCount++;
                }

                $this->info("Auto-Close 3-Lapis Proteksi: {$matched->count()} posisi {$ticker} ditutup ({$resultType} @ Rp{$price}, {$exitDate->toDateTimeString()}).");
            } catch (Throwable $e) {
                $this->warn("Gagal auto-close {$ticker}: ".$e->getMessage());
            }
        }

        return $closedCount;
    }
}
