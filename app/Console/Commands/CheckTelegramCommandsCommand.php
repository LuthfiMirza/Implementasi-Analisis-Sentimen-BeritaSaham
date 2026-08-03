<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase AC (lanjutan): polls Telegram for /open, /close, /status commands sent to the bot and
 * applies them to quant/drawdown_bounce_tracker/open_positions.json -- lets the user manage
 * which positions are being trailing-stop-monitored directly from their phone, without going
 * through Claude in chat every time. Long-polling (getUpdates), not a webhook -- no public HTTPS
 * endpoint needed. Deliberately thin, matching the pattern used by the other research:* commands.
 */
class CheckTelegramCommandsCommand extends Command
{
    protected $signature = 'research:check-telegram-commands';

    protected $description = 'Poll Telegram for /open, /close, /status commands and update open_positions.json';

    public function handle(): int
    {
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
}
