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
        $this->reconcileOpenPositions();

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
        $this->syncTelegramSkipsToTradeJournal($outputLines);

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
     * Fase DF: jembatan tombol "⏭️ Skip" (Telegram) -> web Trade Journal. telegram_commands.py
     * mencetak "SYNC_SKIP|TICKER|STRATEGI|TANGGAL_ENTRY" begitu user tap Skip di alert sinyal --
     * di sini kita HAPUS SEPENUHNYA record `trades` yang cocok (bukan close/tutup spt SYNC_CLOSE
     * -- Skip artinya "saya tidak pernah niat ikuti sinyal ini", jadi trade auto-tercipta itu
     * seharusnya TIDAK PERNAH ada di journal sama sekali, beda semantik dari "saya ikuti lalu
     * keluar"). Dicocokkan via (ticker, strategy_label, entry_date) -- 3 field itu identifier unik
     * yang SAMA dipakai register_open_position() di detect_signal.py buat dedup posisi, jadi
     * matching di sini konsisten dgn sumber kebenaran yang sama.
     *
     * HANYA hapus trade berstatus 'open' -- kalau trade itu SUDAH ditutup (mis. user sempat
     * /close duluan sebelum sempat tap Skip, race condition kecil tapi mungkin), JANGAN hapus
     * riwayat closed yang sah, cukup log peringatan.
     */
    private function syncTelegramSkipsToTradeJournal(array $outputLines): void
    {
        foreach ($outputLines as $line) {
            if (! str_starts_with($line, 'SYNC_SKIP|')) {
                continue;
            }

            [, $ticker, $strategy, $entryDateStr] = array_pad(explode('|', $line), 4, null);
            if (! $ticker || ! $strategy || ! $entryDateStr) {
                continue;
            }

            try {
                $strategyLabelColumn = match ($strategy) {
                    'MOMENTUM' => 'momentum',
                    'BOTTOM_REBOUND' => 'bottom_rebound',
                    default => 'gabungan',
                };

                $trade = Trade::where('ticker', $ticker)
                    ->where('strategy_label', $strategyLabelColumn)
                    ->whereDate('entry_date', $entryDateStr)
                    ->where('status', 'open')
                    ->first();

                if (! $trade) {
                    $this->warn("Sync Trade Journal (skip): tidak ada posisi OPEN {$ticker} [{$strategy}] entry {$entryDateStr} di web -- dilewati.");

                    continue;
                }

                $trade->delete();
                $this->info("Sync Trade Journal: {$ticker} [{$strategy}] entry {$entryDateStr} dihapus dari web (di-skip via Telegram).");
            } catch (Throwable $e) {
                $this->warn("Sync Trade Journal (skip) gagal untuk {$ticker} (DB mungkin mati): ".$e->getMessage());
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

    /** Orphan open_positions.json entry lebih tua dari ini + ticker tak punya posisi open -> dibuang. */
    private const RECONCILE_ORPHAN_STALE_DAYS = 7;

    /**
     * Fase DT: sinkron open_positions.json balik ke Trade Journal MySQL (sumber kebenaran).
     *
     * Ditemukan live (user 2 Sep 2026): bot terus kirim alert "TARGET WAKTU"/"PUNCAK BARU" untuk
     * BUMI/DSSA/ESSA yang user sudah tutup, karena open_positions.json tidak pernah disinkron balik
     * ketika trade ditutup lewat jalur SELAIN Telegram /close (tombol web Trade Journal, closeout
     * batch, dll). Snapshot 2 Sep: 25 entri di JSON, cuma 7 yang benar-benar `open` di DB.
     *
     * Kunci cocok: (ticker, strategy, entry_date) -- sama seperti dedup register_open_position()
     * di detect_signal.py. Buang entri kalau:
     *   1. punya pasangan trade `closed` (bukti positif sudah ditutup), ATAU
     *   2. TIDAK punya pasangan trade sama sekali (orphan) DAN entry_date > 7 hari DAN ticker+
     *      strategi itu tidak punya satu pun posisi `open` di DB -- ini nyapu sinyal lama yang
     *      Trade-row-nya gagal dibuat. Orphan yang MASIH muda atau ticker+strateginya masih punya
     *      posisi open (mis. sinyal kena batas pyramiding Fase DJ -- sengaja dialert tanpa row DB)
     *      DIBIARKAN.
     * Kalau DB mati / 0 trade, skip total (open_positions.json memang dirancang tahan MySQL mati).
     */
    private function reconcileOpenPositions(): void
    {
        $path = base_path('quant/drawdown_bounce_tracker/open_positions.json');
        if (! is_file($path)) {
            return;
        }

        try {
            $tracked = Trade::query()
                ->whereIn('status', ['open', 'closed'])
                ->get(['ticker', 'strategy_label', 'entry_date', 'status']);

            if ($tracked->isEmpty()) {
                return; // DB kosong/aneh -- jangan sentuh
            }

            $keyFor = fn (Trade $t): string => $this->positionKey($t->ticker, $t->strategy_label, $t->entry_date?->toDateString());
            $closedKeys = $tracked->where('status', 'closed')->mapWithKeys(fn (Trade $t) => [$keyFor($t) => true])->all();
            $openKeys = $tracked->where('status', 'open')->mapWithKeys(fn (Trade $t) => [$keyFor($t) => true])->all();
            $openTickerStrategy = $tracked->where('status', 'open')
                ->mapWithKeys(fn (Trade $t) => [strtolower($t->ticker).'|'.strtolower((string) ($t->strategy_label ?: 'gabungan')) => true])
                ->all();

            $positions = json_decode((string) file_get_contents($path), true);
            if (! is_array($positions)) {
                return;
            }

            $staleBefore = Carbon::now()->subDays(self::RECONCILE_ORPHAN_STALE_DAYS);
            $removed = [];

            $kept = array_values(array_filter($positions, function (array $p) use ($closedKeys, $openKeys, $openTickerStrategy, $staleBefore, &$removed): bool {
                $key = $this->positionKey($p['ticker'] ?? '', $p['strategy'] ?? 'GABUNGAN', $p['entry_date'] ?? null);

                // (1) trade-nya sudah closed
                if (isset($closedKeys[$key]) && ! isset($openKeys[$key])) {
                    $removed[] = "{$key} (closed)";

                    return false;
                }

                // (2) orphan lama tanpa posisi open utk ticker+strategi itu
                $hasAnyTrade = isset($closedKeys[$key]) || isset($openKeys[$key]);
                if (! $hasAnyTrade) {
                    $tickerStrategy = strtolower((string) ($p['ticker'] ?? '')).'|'.strtolower((string) ($p['strategy'] ?? 'gabungan'));
                    $entry = isset($p['entry_date']) ? Carbon::parse($p['entry_date']) : null;
                    if ($entry !== null && $entry->lt($staleBefore) && ! isset($openTickerStrategy[$tickerStrategy])) {
                        $removed[] = "{$key} (orphan basi)";

                        return false;
                    }
                }

                return true;
            }));

            if ($removed !== []) {
                file_put_contents($path, json_encode($kept, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
                $this->info('reconcile open_positions.json: '.count($removed).' entri dibuang -> '.implode(', ', $removed));
            }
        } catch (Throwable $e) {
            $this->warn('Gagal reconcile open_positions.json (DB mungkin mati): '.$e->getMessage());
        }
    }

    private function positionKey(?string $ticker, ?string $strategy, ?string $entryDate): string
    {
        return strtolower(trim((string) $ticker))
            .'|'.strtolower(trim((string) ($strategy ?: 'gabungan')))
            .'|'.(string) $entryDate;
    }
}
