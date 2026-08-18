<?php

namespace App\Console\Commands;

use App\Models\Stock;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

class SyncStockLogosCommand extends Command
{
    protected $signature = 'stocks:sync-logos
        {--force : Timpa logo_url yang sudah ada, bukan cuma yang masih kosong}';

    protected $description = 'Ambil logo emiten resmi dari CDN publik TradingView (scanner.tradingview.com untuk logoid, s3-symbol-logo.tradingview.com untuk gambar SVG)';

    public function handle(): int
    {
        $force = (bool) $this->option('force');

        $stocks = Stock::where('is_active', true)
            ->when(! $force, fn ($q) => $q->whereNull('logo_url'))
            ->orderBy('code')
            ->get();

        if ($stocks->isEmpty()) {
            $this->info('Tidak ada saham yang perlu disinkronkan (semua sudah punya logo_url, pakai --force untuk timpa ulang).');

            return self::SUCCESS;
        }

        $this->info("Sinkronisasi logo untuk {$stocks->count()} saham...");
        $ok = 0;
        $fail = 0;

        foreach ($stocks as $stock) {
            try {
                // scanner.tradingview.com: endpoint publik yang dipakai widget TradingView sendiri
                // buat kasih tahu "logoid" per simbol -- BEDA dari symbol-search.tradingview.com
                // yang diblokir bot-protection (403). Header Origin/User-Agent wajib disertakan,
                // tanpa itu request juga ditolak.
                $response = Http::withHeaders([
                    'User-Agent' => 'Mozilla/5.0',
                    'Origin' => 'https://www.tradingview.com',
                ])->timeout(10)->get('https://scanner.tradingview.com/symbol', [
                    'symbol' => "IDX:{$stock->code}",
                    'fields' => 'logoid,description',
                ]);

                $logoid = $response->json('logoid');
                if (! $response->ok() || ! $logoid) {
                    $this->warn("  {$stock->code}: logoid tidak ditemukan, dilewati.");
                    $fail++;

                    continue;
                }

                $logoUrl = "https://s3-symbol-logo.tradingview.com/{$logoid}--big.svg";

                // Verifikasi gambar beneran ada sebelum disimpan -- jangan simpan URL yang bisa
                // jadi 404 di kemudian hari, itu sama saja dengan menebak tanpa verifikasi.
                $imgCheck = Http::timeout(10)->get($logoUrl);
                if (! $imgCheck->ok()) {
                    $this->warn("  {$stock->code}: logoid '{$logoid}' ditemukan tapi gambar tidak bisa diakses (HTTP {$imgCheck->status()}), dilewati.");
                    $fail++;

                    continue;
                }

                $stock->update(['logo_url' => $logoUrl]);
                $this->line("  {$stock->code}: OK ({$logoid})");
                $ok++;
            } catch (\Throwable $e) {
                $this->warn("  {$stock->code}: error -- {$e->getMessage()}");
                $fail++;
            }
        }

        $this->info("Selesai: {$ok} berhasil, {$fail} dilewati.");

        return self::SUCCESS;
    }
}
