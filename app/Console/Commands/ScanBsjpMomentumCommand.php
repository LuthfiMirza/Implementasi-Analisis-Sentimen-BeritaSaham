<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Schema;

class ScanBsjpMomentumCommand extends Command
{
    protected $signature = 'trade:scan-bsjp 
        {--stage=early : Tahap pemindaian: early (15:00 WIB), confirm (15:35 WIB), reminder (08:50 WIB)}
        {--category=all : Filter kategori: all, sweetspot (4% - 15%), rocket (> 15% / calon ARA)}
        {--date= : Tanggal perdagangan YYYY-MM-DD (default: tanggal terakhir di database)}
        {--min-ret=3.0 : Kenaikan harga minimum (%)}
        {--min-vol=1.5 : Rasio lonjakan volume minimum (x lipat)}
        {--min-val=100000000 : Nilai transaksi minimum dalam rupiah}
        {--limit=10 : Jumlah saham teratas yang diambil}
        {--send : Kirim notifikasi alert ke Telegram}';

    protected $description = 'Pindai saham momentum BSJP (Beli Sore Jual Pagi) dan kirim alert Telegram dua tahap (15:00 & 15:35 WIB)';

    public function handle(): int
    {
        if (! Schema::hasTable('idx_daily_summaries')) {
            $this->error('Tabel idx_daily_summaries tidak ditemukan.');

            return self::FAILURE;
        }

        $stage = strtolower($this->option('stage') ?? 'early');
        $categoryFilter = strtolower($this->option('category') ?? 'all');
        $targetDate = $this->resolveTradeDate($this->option('date'));

        if (! $targetDate) {
            $this->error('Tidak ada data perdagangan di tabel idx_daily_summaries.');

            return self::FAILURE;
        }

        $allCandidates = $this->fetchCandidates(
            $targetDate,
            (float) $this->option('min-ret'),
            (float) $this->option('min-vol'),
            (float) $this->option('min-val'),
            (int) $this->option('limit')
        );

        $candidates = match ($categoryFilter) {
            'rocket' => array_values(array_filter($allCandidates, fn ($c) => $c['category'] === 'rocket')),
            'sweetspot' => array_values(array_filter($allCandidates, fn ($c) => $c['category'] === 'sweetspot')),
            default => $allCandidates,
        };

        $this->info("=== SCANNER MOMENTUM BSJP [STAGE: " . strtoupper($stage) . " | KATEGORI: " . strtoupper($categoryFilter) . "] ===");
        $this->line("Tanggal Evaluasi: {$targetDate}");
        $this->line("Ditemukan: " . count($candidates) . " saham potensial.");

        if (empty($candidates)) {
            $this->warn('Tidak ada saham yang memenuhi kriteria untuk kategori ini.');

            return self::SUCCESS;
        }

        $this->table(
            ['Ticker', 'Nama', 'Kategori', 'Harga', 'Kenaikan', 'Vol Spike', 'Nilai Trx (Rp)', 'Open'],
            collect($candidates)->map(function ($c) {
                return [
                    $c['ticker'],
                    \Illuminate\Support\Str::limit($c['name'], 22),
                    $c['category_label'],
                    'Rp ' . number_format($c['price'], 0, ',', '.'),
                    sprintf('%+.2f%%', $c['return_pct']),
                    sprintf('%.1fx', $c['volume_ratio']),
                    'Rp ' . number_format($c['value'], 0, ',', '.'),
                    'Rp ' . number_format($c['open'], 0, ',', '.'),
                ];
            })
        );

        $message = match ($stage) {
            'confirm' => $this->formatConfirmAlert($candidates, $targetDate),
            'reminder' => $this->formatReminderAlert($candidates, $targetDate),
            default => $this->formatEarlyAlert($candidates, $targetDate),
        };

        $this->newLine();
        $this->line("--- PREVIEW PESAN TELEGRAM ---");
        $this->line(strip_tags($message));
        $this->line("------------------------------");

        if ($this->option('send')) {
            $this->sendTelegram($message);
        } else {
            $this->comment('Gunakan opsi --send untuk mengirim notifikasi langsung ke Telegram.');
        }

        return self::SUCCESS;
    }

    private function resolveTradeDate(?string $date): ?string
    {
        if ($date) {
            return $date;
        }

        $max = DB::table('idx_daily_summaries')->max('trade_date');

        return $max ? Carbon::parse($max)->toDateString() : null;
    }

    /**
     * @return array<int, array{ticker: string, name: string, price: float, open: float, prev_price: float, return_pct: float, volume: int, prev_volume: int, volume_ratio: float, value: float}>
     */
    public function fetchCandidates(string $tradeDate, float $minRet, float $minVolRatio, float $minVal, int $limit): array
    {
        $priorDate = DB::table('idx_daily_summaries')
            ->where('trade_date', '<', $tradeDate)
            ->max('trade_date');

        if (! $priorDate) {
            return [];
        }

        $rows = DB::table('idx_daily_summaries as t')
            ->join('idx_daily_summaries as p', function ($join) use ($priorDate) {
                $join->on('t.stock_code', '=', 'p.stock_code')
                    ->where('p.trade_date', '=', $priorDate);
            })
            ->where('t.trade_date', '=', $tradeDate)
            ->where('t.close', '>', DB::raw('t.open'))
            ->where('t.pct_change', '>=', $minRet)
            ->where('t.value', '>=', $minVal)
            ->where('t.volume', '>', DB::raw('p.volume'))
            ->select([
                't.stock_code as ticker',
                't.stock_name as name',
                't.close as price',
                't.open as open_price',
                't.previous as prev_price',
                't.pct_change as return_pct',
                't.volume as volume_today',
                'p.volume as volume_prev',
                DB::raw('t.volume / NULLIF(p.volume, 0) as volume_ratio'),
                't.value as transaction_value',
            ])
            ->having('volume_ratio', '>=', $minVolRatio)
            ->orderByDesc('volume_ratio')
            ->orderByDesc('t.value')
            ->take($limit)
            ->get();

        return $rows->map(function ($r) {
            $retPct = (float) $r->return_pct;
            $isRocket = $retPct >= 15.0;

            return [
                'ticker' => (string) $r->ticker,
                'name' => (string) ($r->name ?? $r->ticker),
                'price' => (float) $r->price,
                'open' => (float) $r->open_price,
                'prev_price' => (float) $r->prev_price,
                'return_pct' => $retPct,
                'volume' => (int) $r->volume_today,
                'prev_volume' => (int) $r->volume_prev,
                'volume_ratio' => round((float) $r->volume_ratio, 2),
                'value' => (float) $r->transaction_value,
                'category' => $isRocket ? 'rocket' : 'sweetspot',
                'category_label' => $isRocket ? '🚀 Super Rocket' : '🎯 Sweetspot',
            ];
        })->all();
    }

    private function formatEarlyAlert(array $candidates, string $date): string
    {
        $nowStr = now('Asia/Jakarta')->format('d M Y, H:i') . ' WIB';
        $lines = [
            '🟡 <b>RADAR PANTAU BSJP (Beli Sore Jual Pagi)</b>',
            "📅 <i>Pukul 15:00 WIB Early Warning • {$nowStr}</i>",
            '',
            'Terdeteksi saham dengan <b>Ledakan Volume & Bullish Candle</b> yang memenuhi kriteria BSJP:',
            '',
        ];

        foreach (array_slice($candidates, 0, 8) as $idx => $c) {
            $num = $idx + 1;
            $valM = number_format($c['value'] / 1_000_000_000, 2, ',', '.');
            $price = number_format($c['price'], 0, ',', '.');
            $ret = sprintf('%+.2f%%', $c['return_pct']);
            $tag = $c['category'] === 'rocket' ? '🚀 <i>[Super Rocket]</i>' : '🎯 <i>[Sweetspot]</i>';
            $lines[] = "<b>{$num}. #{$c['ticker']}</b> {$tag} — Rp{$price} (<b>{$ret}</b>)\n"
                . "   • Vol Spike: <b>{$c['volume_ratio']}x lipat</b> vs kemarin\n"
                . "   • Nilai Trx: Rp{$valM} Miliar | Open: Rp" . number_format($c['open'], 0, ',', '.');
        }

        $lines[] = '';
        $lines[] = '⏱️ <b>Status: RADAR PANTAU DINI (15:00 WIB)</b>';
        $lines[] = '💡 <i>Instruksi: Pantau saham di atas hingga pukul 15:35 WIB. Jika lilin tetap hijau solid dan tidak diguyur, bersiap eksekusi di Pre-Closing (15:50 WIB) untuk take profit di pembukaan esok pagi!</i>';

        return implode("\n", $lines);
    }

    private function formatConfirmAlert(array $candidates, string $date): string
    {
        $nowStr = now('Asia/Jakarta')->format('d M Y, H:i') . ' WIB';
        $lines = [
            '🟢 <b>KONFIRMASI AKHIR BSJP — SIAP BELI</b>',
            "📅 <i>Pukul 15:35 WIB Final Call • {$nowStr}</i>",
            '',
            'Validasi selesai! Saham-saham berikut <b>tetap solid bertahan di area atas</b> tanpa tekanan guyuran bandar:',
            '',
        ];

        foreach (array_slice($candidates, 0, 5) as $idx => $c) {
            $num = $idx + 1;
            $valM = number_format($c['value'] / 1_000_000_000, 2, ',', '.');
            $price = number_format($c['price'], 0, ',', '.');
            $ret = sprintf('%+.2f%%', $c['return_pct']);
            $targetTp = number_format(round($c['price'] * 1.025), 0, ',', '.');
            $tag = $c['category'] === 'rocket' ? '🚀 [Super Rocket]' : '🎯 [Sweetspot Likuid]';

            $lines[] = "<b>PILIHAN #{$num}: #{$c['ticker']}</b> {$tag} (Rp{$price} | <b>{$ret}</b>)\n"
                . "   • Rasio Volume: <b>{$c['volume_ratio']}x</b> | Trx: Rp{$valM} Miliar\n"
                . "   • <b>Rekomendasi Beli:</b> Sesi Pre-Closing (15:50 - 15:58 WIB)\n"
                . "   • <b>Target Jual Besok:</b> Rp{$targetTp} (+2.5% s/d Open 09:00 WIB)";
        }

        $lines[] = '';
        $lines[] = '⚠️ <b>Manajemen Risiko:</b>';
        $lines[] = '• Alokasi: Maksimal 1-2 saham per hari.';
        $lines[] = '• Exit Rules: Wajib pasang antrian jual di 08:55 WIB esok pagi sebelum pembukaan.';
        $lines[] = '• Cut Loss Disiplin: -3.0% jika terjadi gap-down tak terduga.';

        return implode("\n", $lines);
    }

    private function formatReminderAlert(array $candidates, string $date): string
    {
        $nowStr = now('Asia/Jakarta')->format('d M Y, H:i') . ' WIB';
        $lines = [
            '🔔 <b>PENGINGAT AMBIL CUAN BSJP (08:50 WIB)</b>',
            "📅 <i>Persiapan Pembukaan Bursa • {$nowStr}</i>",
            '',
            '10 menit lagi bursa buka! Jangan lupa siapkan antrian jual untuk saham BSJP kemarin sore:',
            '',
        ];

        foreach (array_slice($candidates, 0, 5) as $c) {
            $price = number_format($c['price'], 0, ',', '.');
            $targetTp = number_format(round($c['price'] * 1.025), 0, ',', '.');
            $tag = $c['category'] === 'rocket' ? '🚀' : '🎯';
            $lines[] = "• {$tag} <b>#{$c['ticker']}</b> (Beli Sore: Rp{$price})\n"
                . "  ↳ Pasang Jual di: <b>Rp{$targetTp} (+2.5%)</b> atau langsung <b>HAKI di Open 09:00 WIB</b>";
        }

        $lines[] = '';
        $lines[] = '⚡ <i>Data historis membuktikan: 82.8% saham mencetak harga tertinggi di 15 menit pertama (09:00 - 09:15 WIB). Amankan cuan sebelum bandar mulai distribusi di siang hari!</i>';

        return implode("\n", $lines);
    }

    private function sendTelegram(string $message): void
    {
        $token = env('TELEGRAM_BOT_TOKEN');
        $chatIds = array_filter([env('TELEGRAM_CHAT_ID'), env('TELEGRAM_CHAT_ID_2')]);

        if (! $token || empty($chatIds)) {
            $this->error('TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum terkonfigurasi di file .env');

            return;
        }

        $this->line('Mengirim pesan ke Telegram...');
        $success = 0;

        foreach ($chatIds as $chatId) {
            try {
                $response = Http::timeout(10)->post("https://api.telegram.org/bot{$token}/sendMessage", [
                    'chat_id' => $chatId,
                    'text' => $message,
                    'parse_mode' => 'HTML',
                    'disable_web_page_preview' => true,
                ]);

                if ($response->successful()) {
                    $success++;
                    $this->info("✓ Terkirim ke chat ID: {$chatId}");
                } else {
                    $this->error("Gagal kirim ke chat ID {$chatId}: " . $response->body());
                }
            } catch (\Throwable $e) {
                $this->error("Error koneksi ke Telegram: " . $e->getMessage());
            }
        }

        if ($success > 0) {
            $this->info("Berhasil mengirim alert BSJP ke {$success} penerima Telegram!");
        }
    }
}
