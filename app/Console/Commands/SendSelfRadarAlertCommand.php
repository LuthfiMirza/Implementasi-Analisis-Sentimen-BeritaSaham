<?php

namespace App\Console\Commands;

use App\Services\Trading\SignalRadarService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

class SendSelfRadarAlertCommand extends Command
{
    protected $signature = 'research:send-self-radar-alert {--send : Kirim ke Telegram. Tanpa flag ini hanya preview.}';

    protected $description = 'Preview/kirim alert Telegram SELF_RADAR_V1 experimental dari halaman Signal Radar';

    public function handle(SignalRadarService $radar): int
    {
        $rows = collect($radar->build()['self_radar'] ?? [])
            ->where('triggered', true)
            ->values();

        if ($rows->isEmpty()) {
            $this->info('SELF_RADAR_V1: tidak ada kandidat BUY SORE INI saat ini.');

            return self::SUCCESS;
        }

        $message = $this->formatMessage($rows->all());
        $this->line($message);

        if (! $this->option('send')) {
            $this->newLine();
            $this->warn('Preview saja. Pakai --send untuk kirim ke Telegram.');

            return self::SUCCESS;
        }

        $token = env('TELEGRAM_BOT_TOKEN');
        $chatIds = array_filter([env('TELEGRAM_CHAT_ID'), env('TELEGRAM_CHAT_ID_2')]);
        if (! $token || $chatIds === []) {
            $this->error('TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID belum lengkap.');

            return self::FAILURE;
        }

        foreach ($chatIds as $chatId) {
            $response = Http::timeout(15)->post("https://api.telegram.org/bot{$token}/sendMessage", [
                'chat_id' => $chatId,
                'text' => $message,
                'parse_mode' => 'HTML',
                'disable_web_page_preview' => true,
            ]);

            if ($response->failed()) {
                $this->error("Gagal kirim ke chat {$chatId}: {$response->body()}");

                return self::FAILURE;
            }
        }

        $this->info('Alert SELF_RADAR_V1 terkirim ke Telegram.');

        return self::SUCCESS;
    }

    private function formatMessage(array $rows): string
    {
        $lines = [
            '🟢 <b>SELF_RADAR_V1 — BUY SORE INI (EXPERIMENTAL)</b>',
            'Bukan sinyal resmi. Test live catatan strategi terpisah.',
            'Rule: RSI14 ≥ 60, ret_5d ≥ 5%, dd_20d ≥ -5%',
            sprintf(
                'Tanggal sinyal: %s. Entry: %s dekat close. Trailing stop 1%% aktif %s WIB.',
                $rows[0]['scan_date'] ?? now()->timezone('Asia/Jakarta')->toDateString(),
                $rows[0]['entry_date'] ?? now()->timezone('Asia/Jakarta')->toDateString(),
                $rows[0]['trailing_start_at'] ?? now()->timezone('Asia/Jakarta')->copy()->addWeekday()->format('Y-m-d 09:30'),
            ),
            '',
        ];

        foreach ($rows as $row) {
            $lines[] = sprintf(
                '<b>%s</b> Rp%s | RSI14 %.2f | ret_5d %.2f%% | dd_20d %.2f%%',
                e($row['ticker']),
                number_format((float) $row['price_now'], 0, ',', '.'),
                (float) $row['rsi14_now'],
                (float) $row['ret_5d_pct'],
                (float) $row['dd_20d_pct'],
            );
        }

        $lines[] = '';
        $lines[] = 'Catat manual sebagai SELF_RADAR_V1, status paper/live kecil dulu; jangan gabung statistik GABUNGAN/MOMENTUM.';

        return implode("\n", $lines);
    }
}
