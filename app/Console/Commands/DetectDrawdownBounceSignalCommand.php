<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\Trade;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;
use Throwable;

/**
 * Fase AC: daily automatic detector for the "IHSG + stock crash together" bounce rule found in
 * Fase AB's historical backtest (BUMI: 27 independent episodes, consistently positive discovery
 * and holdout -- the most credible finding this project has produced so far; DEWA: only 18
 * episodes, 26% from a single month, exploratory only). See
 * quant/drawdown_bounce_tracker/PROTOCOL.md, locked before this command's first real run.
 *
 * Deliberately thin -- all detection logic lives in the Python script (fetches BUMI/DEWA/IHSG
 * directly from yfinance, no DB dependency), matching the pattern used by
 * research:collect-foreign-flow and prediction:refresh-price-history.
 */
class DetectDrawdownBounceSignalCommand extends Command
{
    protected $signature = 'research:detect-drawdown-bounce-signal';

    protected $description = 'Detect new IHSG+stock drawdown-bounce signals for BUMI/DEWA (Fase AB/AC, prospective tracker)';

    /**
     * Fase BM: modal simulasi tetap Rp10jt per posisi live -- BUKAN compounding seperti backfill
     * historis (Opsi A), karena live entries dibuat satu-satu tanpa tahu urutan "modal berjalan"
     * di muka. Beda gaya sengaja, dijelaskan eksplisit di notes tiap trade supaya tidak
     * membingungkan saat dibandingkan dengan baris backfill.
     */
    private const LIVE_CAPITAL = 10_000_000.0;

    // Fase DG: universe ticker yg dicek beritanya -- SAMA PERSIS gabungan
    // SignalRadarService::GABUNGAN_TICKERS + MOMENTUM_TICKERS + BOTTOM_REBOUND_TICKERS (Fase
    // DB/DC). Di-hardcode terpisah (bukan reuse class itu) supaya command ini TETAP jalan mandiri
    // tanpa dependency ke App\Services\Trading -- kalau daftar ticker berubah di sana, WAJIB
    // diubah juga di sini (dicek manual, tidak ada single-source-of-truth constant bersama --
    // trade-off kesederhanaan vs duplikasi kecil, 11 ticker jarang berubah).
    private const NEWS_CONTEXT_TICKERS = ['BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'TINS', 'PTRO', 'ENRG', 'RAJA', 'DSSA'];

    public function handle(): int
    {
        // Fase DG: News-in-Signal -- cache berita+sentimen terbaru per ticker DITULIS SEBELUM
        // python script jalan (pola sama persis refreshClosedTradesCache() di
        // CheckTelegramCommandsCommand.php). detect_signal.py SENGAJA tidak pernah query MySQL
        // langsung (resilience pattern -- lihat docstring lama di telegram_commands.py), jadi PHP
        // (yg SUDAH asumsikan DB nyala saat command artisan ini jalan) yg jembatani datanya lewat
        // file cache, bukan python connect ke MySQL sendiri.
        $this->refreshNewsContextCache();

        $python = env('PYTHON_BINARY', 'python3');
        $script = base_path('quant/drawdown_bounce_tracker/detect_signal.py');

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

        $this->syncOpenSignalsToTradeJournal($outputLines);

        if (! $result->successful()) {
            $this->error('Gagal mendeteksi sinyal: '.trim($result->errorOutput()));

            return self::FAILURE;
        }

        return self::SUCCESS;
    }

    /**
     * Fase BM: jembatan sinyal live -> web Trade Journal (pasangan dari SYNC_CLOSE Fase BJ yang
     * sudah ada). detect_signal.py mencetak "SYNC_OPEN|TICKER|HARGA|TANGGAL|STRATEGI|DETAIL"
     * begitu sinyal baru terdaftar ke open_positions.json -- di sini kita buat record `trades`
     * status 'open' berlabel LIVE (BUKAN simulasi) supaya sinyal live otomatis kelihatan di
     * Trade Journal tanpa perlu /open manual dulu. Penutupannya reuse jembatan SYNC_CLOSE yang
     * sudah ada di CheckTelegramCommandsCommand -- tidak perlu logika baru untuk exit.
     */
    private function syncOpenSignalsToTradeJournal(array $outputLines): void
    {
        foreach ($outputLines as $line) {
            if (! str_starts_with($line, 'SYNC_OPEN|')) {
                continue;
            }

            [, $ticker, $price, $dateStr, $strategy, $detail] = array_pad(explode('|', $line), 6, null);
            if (! $ticker || ! is_numeric($price)) {
                continue;
            }

            try {
                $stock = Stock::where('code', $ticker)->first();
                if (! $stock) {
                    $this->warn("Sync Trade Journal (open): saham {$ticker} tidak ditemukan di tabel stocks -- dilewati.");
                    continue;
                }

                $exists = Trade::where('ticker', $ticker)
                    ->whereDate('entry_date', $dateStr)
                    ->where('notes', 'like', 'LIVE — sinyal otomatis%')
                    ->exists();
                if ($exists) {
                    continue; // idempotent -- jangan dobel kalau command jalan ulang
                }

                $entryPrice = (float) $price;
                $quantity = (int) (floor(self::LIVE_CAPITAL / $entryPrice / 100) * 100);
                if ($quantity <= 0) {
                    $quantity = 100;
                }

                // Fase CS: dulu ternary 2-cabang (MOMENTUM vs default-ke-GABUNGAN) -- aman selama
                // cuma ada 2 strategi otomatis. Begitu BOTTOM_REBOUND ditambah, default itu jadi
                // BAHAYA DIAM-DIAM: sinyal strategi baru bakal salah tercatat 'gabungan' dan
                // mengotori statistik resmi GABUNGAN tanpa error apapun. match() eksplisit --
                // strategi baru ke depan WAJIB ditambah di sini dulu, tidak boleh jatuh ke default.
                $strategyLabel = match ($strategy) {
                    'MOMENTUM' => "MOMENTUM ({$detail})",
                    'BOTTOM_REBOUND' => "BOTTOM-REBOUND ({$detail})",
                    default => 'GABUNGAN, jenis: '.($detail ?: 'ret2d'),
                };
                $strategyLabelColumn = match ($strategy) {
                    'MOMENTUM' => 'momentum',
                    'BOTTOM_REBOUND' => 'bottom_rebound',
                    default => 'gabungan',
                };

                Trade::create([
                    'user_id' => 2,
                    'stock_id' => $stock->id,
                    'ticker' => $ticker,
                    'direction' => 'long',
                    'signal_quality' => 'journal',
                    'entry_price' => $entryPrice,
                    'stop_loss' => round($entryPrice * (1 - 0.02), 2),
                    'target_1' => round($entryPrice * (1 + 0.05), 2),
                    // lot_size di kolom DB menyimpan LEMBAR (bukan jumlah lot) -- konvensi yang
                    // sama dipakai TradeController::store() untuk trade manual via form web
                    // (lihat LEMBAR_PER_LOT), "Lot" yang ditampilkan di UI itu lot_size/100.
                    'lot_size' => $quantity,
                    'quantity' => $quantity,
                    'position_value' => round($quantity * $entryPrice, 2),
                    'status' => 'open',
                    'entry_date' => $dateStr,
                    'trade_date' => $dateStr,
                    'result' => 'open',
                    'notes' => "LIVE — sinyal otomatis {$strategyLabel}. Modal simulasi tetap Rp10.000.000 ".
                        '(bukan compounding). Exit dipantau otomatis via research:check-trailing-stop-alert '.
                        '(trailing stop 2% / target waktu 10 hari) -- posisi ini juga terdaftar di '.
                        'open_positions.json untuk alert Telegram.',
                    // Fase CA: diisi eksplisit saat insert, bukan ditebak dari notes belakangan --
                    // strategy_label='gabungan' inilah yang dihitung ke kartu ringkasan RESMI.
                    'strategy_label' => $strategyLabelColumn,
                ]);

                $this->info("Sync Trade Journal: {$ticker} dibuka otomatis di web (entry Rp{$price}, {$dateStr}, {$strategyLabel}).");
            } catch (Throwable $e) {
                $this->warn("Sync Trade Journal (open) gagal untuk {$ticker} (DB mungkin mati): ".$e->getMessage());
            }
        }
    }

    /**
     * Fase DG: News-in-Signal -- tulis cache 3 berita TERBARU (ANY AGE, tidak dibatasi window
     * ketat -- ticker sepi berita spt DEWA bisa saja terakhir 8 hari lalu, tetap ditampilkan
     * dgn tanggalnya biar user tahu itu "stale", bukan disembunyikan diam-diam jadi "tidak ada
     * berita sama sekali") per ticker yg dipantau, dibaca detect_signal.py buat lampirkan konteks
     * berita ke alert sinyal BELI (cegah beli di saham yg lagi ada bad news padahal technical
     * bagus). `sentiment_label` (BUKAN ml_sentiment_label) -- field yg sama dipakai halaman /news
     * publik (resources/views/news/index.blade.php), sudah "final" method output (rule-based/
     * hybrid), konsisten dgn yg user lihat di web.
     *
     * Kegagalan (DB mati dst) TIDAK BOLEH menggagalkan seluruh command -- deteksi sinyal +
     * alert dasar (tanpa konteks berita) harus tetap jalan, News-in-Signal murni tambahan.
     */
    private function refreshNewsContextCache(): void
    {
        $cachePath = base_path('quant/drawdown_bounce_tracker/news_context_cache.json');

        try {
            $context = [];
            foreach (self::NEWS_CONTEXT_TICKERS as $ticker) {
                $stock = Stock::where('code', $ticker)->first();
                if (! $stock) {
                    $context[$ticker] = [];
                    continue;
                }

                $context[$ticker] = NewsArticle::where('stock_id', $stock->id)
                    ->whereNotNull('sentiment_label')
                    ->whereNotNull('published_at')
                    ->orderByDesc('published_at')
                    ->limit(3)
                    ->get(['title', 'sentiment_label', 'published_at'])
                    ->map(fn (NewsArticle $a) => [
                        'title' => $a->title,
                        'sentiment' => $a->sentiment_label,
                        'published_at' => $a->published_at->toIso8601String(),
                    ])
                    ->values()->all();
            }

            file_put_contents($cachePath, json_encode($context, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
        } catch (Throwable $e) {
            $this->warn('Gagal refresh cache konteks berita (DB mungkin mati): '.$e->getMessage());
        }
    }
}
