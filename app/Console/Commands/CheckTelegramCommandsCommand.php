<?php

namespace App\Console\Commands;

use App\Models\Trade;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;
use Throwable;

/**
 * Fase AC (lanjutan): polls Telegram for /open, /close, /status, /history commands sent to the
 * bot and applies them to quant/drawdown_bounce_tracker/open_positions.json -- lets the user
 * manage which positions are being trailing-stop-monitored directly from their phone, without
 * going through Claude in chat every time. Long-polling (getUpdates), not a webhook -- no public
 * HTTPS endpoint needed. Deliberately thin, matching the pattern used by the other research:*
 * commands.
 */
class CheckTelegramCommandsCommand extends Command
{
    protected $signature = 'research:check-telegram-commands';

    protected $description = 'Poll Telegram for /open, /close, /status, /history commands and update open_positions.json';

    public function handle(): int
    {
        $this->refreshClosedTradesCache();

        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/telegram_commands.py');

        if (! is_file($script)) {
            $this->error("Script tidak ditemukan: {$script}");

            return self::FAILURE;
        }

        $result = Process::timeout(30)->run([$python, $script]);

        foreach (explode("\n", trim($result->output())) as $line) {
            if ($line !== '') {
                $this->line($line);
            }
        }

        if (! $result->successful()) {
            $this->error('Gagal cek perintah Telegram: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }

    /**
     * Fase AH: writes the last 10 closed trades to a JSON cache the Python script can read for
     * /history -- telegram_commands.py deliberately never touches MySQL directly (same
     * resilience pattern as open_positions.json), so this refresh is the only bridge. If the DB
     * is down (MySQL is manual-start in this project), skip silently and leave the last-known
     * cache in place -- self-heals next run once MySQL is back, matching news:auto-recover-gap.
     */
    private function refreshClosedTradesCache(): void
    {
        $cachePath = base_path('quant/drawdown_bounce_tracker/closed_trades_cache.json');

        try {
            $trades = Trade::query()
                ->where('status', 'closed')
                ->orderByDesc('exit_date')
                ->limit(10)
                ->get(['ticker', 'entry_price', 'exit_price', 'entry_date', 'exit_date', 'holding_days', 'lot_size', 'pnl_total', 'pnl_percent', 'result'])
                ->map(fn (Trade $trade) => [
                    'ticker' => $trade->ticker,
                    'entry_price' => $trade->entry_price,
                    'exit_price' => $trade->exit_price,
                    'entry_date' => $trade->entry_date?->toDateString(),
                    'exit_date' => $trade->exit_date?->toDateString(),
                    'holding_days' => $trade->holding_days,
                    'lot_size' => $trade->lot_size,
                    'pnl_total' => $trade->pnl_total,
                    'pnl_percent' => $trade->pnl_percent,
                    'result' => $trade->result,
                ])
                ->values();

            file_put_contents($cachePath, $trades->toJson(JSON_PRETTY_PRINT));
        } catch (Throwable $e) {
            $this->warn('Gagal refresh cache riwayat trade (DB mungkin mati): '.$e->getMessage());
        }
    }
}
