<?php

namespace App\Console\Commands;

use App\Models\Trade;
use Carbon\Carbon;
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

        $outputLines = explode("\n", trim($result->output()));
        foreach ($outputLines as $line) {
            if ($line !== '') {
                $this->line($line);
            }
        }

        $this->syncTelegramClosesToTradeJournal($outputLines);

        if (! $result->successful()) {
            $this->error('Gagal cek perintah Telegram: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }

    /**
     * Fase BJ: jembatan Telegram /close -> web Trade Journal. telegram_commands.py mencetak baris
     * "SYNC_CLOSE|TICKER|PRICE|TANGGAL" ke stdout begitu /close berhasil menghapus posisi dari
     * open_positions.json -- di sini kita parse baris itu dan tutup record `trades` yang cocok
     * (ticker sama, status masih open, entry_date PALING BARU kalau ada lebih dari satu -- jarang
     * terjadi tapi mungkin kalau user re-entry sebelum yang lama sempat ditutup di web). Kalau
     * DB mati atau tidak ada record open yang cocok, skip diam-diam dengan peringatan -- jangan
     * sampai kegagalan sinkronisasi ini menggagalkan keseluruhan command (alert Telegram tetap
     * harus jalan meski MySQL lagi mati).
     */
    private function syncTelegramClosesToTradeJournal(array $outputLines): void
    {
        foreach ($outputLines as $line) {
            if (! str_starts_with($line, 'SYNC_CLOSE|')) {
                continue;
            }

            [, $ticker, $price, $dateStr] = array_pad(explode('|', $line), 4, null);
            if (! $ticker || ! is_numeric($price)) {
                continue;
            }

            try {
                $trade = Trade::where('ticker', $ticker)
                    ->where('status', 'open')
                    ->orderByDesc('entry_date')
                    ->first();

                if (! $trade) {
                    $this->warn("Sync Trade Journal: tidak ada posisi OPEN {$ticker} di web -- dilewati (mungkin belum pernah dicatat di sana).");
                    continue;
                }

                $exitDate = $dateStr ? Carbon::parse($dateStr) : Carbon::now();
                $trade->close((float) $price, 'manual_close', $exitDate);
                $this->info("Sync Trade Journal: {$ticker} ditutup otomatis di web (exit Rp{$price}, {$exitDate->toDateString()}).");
            } catch (Throwable $e) {
                $this->warn("Sync Trade Journal gagal untuk {$ticker} (DB mungkin mati): ".$e->getMessage());
            }
        }
    }

    /**
     * Fase AH: writes the last 10 closed trades to a JSON cache the Python script can read for
     * /history -- telegram_commands.py deliberately never touches MySQL directly (same
     * resilience pattern as open_positions.json), so this refresh is the only bridge. If the DB
     * is down (MySQL is manual-start in this project), skip silently and leave the last-known
     * cache in place -- self-heals next run once MySQL is back, matching news:auto-recover-gap.
     */
    /**
     * Fase BJ (lanjutan): user bandingkan /history di Telegram (dulu cuma total dari 10 posisi
     * terakhir) dengan ringkasan di web /trades (total dari SEMUA trade) -- angkanya beda jauh
     * dan membingungkan. Cache sekarang bawa 2 bagian: `overall` (dihitung dari SEMUA trade
     * closed, sama persis basisnya dengan kartu ringkasan web) dan `recent` (10 detail terakhir,
     * tetap dibatasi 10 biar tidak kepanjangan di chat). format_history() di telegram_commands.py
     * menampilkan overall sebagai ringkasan utama, recent sebagai daftar di bawahnya.
     */
    private function refreshClosedTradesCache(): void
    {
        $cachePath = base_path('quant/drawdown_bounce_tracker/closed_trades_cache.json');

        try {
            $closed = Trade::query()->where('status', 'closed')->get();
            $wins = $closed->where('pnl_total', '>', 0);
            $losses = $closed->where('pnl_total', '<=', 0);

            $overall = [
                'total_trades' => $closed->count(),
                'win_count' => $wins->count(),
                'loss_count' => $losses->count(),
                'win_rate' => $closed->count() > 0 ? round($wins->count() / $closed->count() * 100, 1) : 0,
                'total_pnl' => (float) $closed->sum('pnl_total'),
                'avg_rr' => round((float) $closed->avg('actual_rr'), 2),
                'expectancy' => $closed->count() > 0 ? round((float) $closed->avg('pnl_percent'), 2) : 0,
                'avg_holding' => $closed->count() > 0 ? round((float) $closed->avg('holding_days'), 1) : 0,
            ];

            $recent = $closed
                ->sortByDesc('exit_date')
                ->take(10)
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

            file_put_contents($cachePath, json_encode([
                'overall' => $overall,
                'recent' => $recent,
            ], JSON_PRETTY_PRINT));
        } catch (Throwable $e) {
            $this->warn('Gagal refresh cache riwayat trade (DB mungkin mati): '.$e->getMessage());
        }
    }
}
