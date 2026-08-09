<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Fase BA: peringatan AWAL (bukan sinyal resmi) di sesi 1 (~12:00 WIB) untuk saham yang
 * dipantau. Murni informasional -- tidak mengubah aturan trigger/entry resmi sama sekali (itu
 * tetap di research:detect-drawdown-bounce-signal, closing 15:18, entry T+1). Backtest Fase AZ
 * membuktikan entry lebih cepat (pakai harga sesi 1) justru menurunkan win rate tanpa menambah
 * return, jadi usulan itu ditolak -- ini cuma heads-up, bukan perubahan strategi.
 */
class CheckSession1WarningCommand extends Command
{
    protected $signature = 'research:check-session1-warning';

    protected $description = 'Kirim peringatan awal (bukan sinyal resmi) kalau saham yang dipantau sudah menembus ambang -5%/2hari di sesi 1 (Fase BA)';

    public function handle(): int
    {
        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/check_session1_warning.py');

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
            $this->error('Gagal cek peringatan sesi 1: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }
}
