<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Process;

class BroadcastSentimenaSoreCommand extends Command
{
    protected $signature = 'trade:broadcast-sentimena-sore 
        {--date= : Tanggal perdagangan YYYY-MM-DD (default: tanggal terbaru)}
        {--send : Kirim notifikasi alert ke Telegram}';

    protected $description = 'Kirim broadcast rangkuman terpadu SENTIMENA SORE (Juara 1 BSJP, Tiket Emas V1, Juara 2 Gabungan, Juara 3 Momentum, & Trailing Stop) jam 15:36 WIB';

    public function handle(): int
    {
        $date = $this->option('date');
        if (! $date) {
            $latest = DB::table('idx_daily_summaries')->max('trade_date');
            $date = $latest ? Carbon::parse($latest)->toDateString() : now('Asia/Jakarta')->toDateString();
        }

        $this->info("Menyiapkan Broadcast Sentimena Sore untuk tanggal: {$date}");

        $cmd = ['python3', base_path('quant/send_sentimena_sore_broadcast.py'), "--date={$date}"];
        if ($this->option('send')) {
            $cmd[] = '--send';
        }

        $result = Process::path(base_path())
            ->timeout(60)
            ->run($cmd);

        if ($result->successful()) {
            $this->line($result->output());
            $this->info('Broadcast Sentimena Sore berhasil diproses.');
            return self::SUCCESS;
        }

        $this->error('Gagal menjalankan script broadcast: ' . $result->errorOutput());
        return self::FAILURE;
    }
}
