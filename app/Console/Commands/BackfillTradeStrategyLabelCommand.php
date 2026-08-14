<?php

namespace App\Console\Commands;

use App\Models\Trade;
use Illuminate\Console\Command;

/**
 * Fase CA: sebelum kolom `strategy_label` ada, satu-satunya cara tahu strategi sebuah trade
 * adalah menebak dari teks `notes` -- rapuh (contoh nyata: match substring 'ai' salah tangkap
 * kata Indonesia biasa, membuat kartu ringkasan "AI-tp30" tercampur 82 trade padahal aslinya
 * cuma 15). Command ini SEKALI JALAN mengisi `strategy_label` untuk trade yang sudah ada,
 * berdasarkan pola notes PERSIS (bukan substring longgar) yang diverifikasi manual dulu.
 *
 * Idempotent -- aman dijalankan ulang, cuma mengisi baris yang strategy_label-nya masih null.
 */
class BackfillTradeStrategyLabelCommand extends Command
{
    protected $signature = 'trades:backfill-strategy-label {--dry-run : Tampilkan saja, jangan simpan}';

    protected $description = 'Isi strategy_label untuk trade lama berdasarkan pola notes (sekali jalan, idempotent)';

    /**
     * Urutan array ini PENTING -- pola lebih spesifik harus dicek duluan (mis. 'AI tp' sebelum
     * pola drawdown-bounce generik) supaya tidak salah tangkap.
     */
    private const PATTERNS = [
        'gabungan' => ['aturan GABUNGAN', 'sinyal otomatis GABUNGAN', 'Entry sesuai sinyal GABUNGAN'],
        'legacy_stock_only' => ['strategi drawdown-bounce stock-only'],
        'legacy_ab_ac' => ['aturan drawdown-bounce (Fase AB/AC)'],
        'ai_tp30' => ['strategi AI tp'],
        'momentum' => ['sinyal otomatis MOMENTUM'],
    ];

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $trades = Trade::whereNull('strategy_label')->get();

        // Diklasifikasi di MEMORI dulu (bukan re-query DB) supaya --dry-run akurat -- kalau
        // pass kedua re-query 'whereNull', baris yang belum disimpan (mode dry-run) akan
        // ketangkap LAGI sebagai "belum diklasifikasi", menggandakan hitungan.
        $counts = [];
        foreach ($trades as $trade) {
            // Sisa yang tidak cocok pola manapun -- termasuk "Entry setelah.../Re-entry..."
            // (trade manual naratif) dan apa pun yang belum pernah diverifikasi. Ditandai
            // eksplisit 'manual_discretionary' daripada dibiarkan null selamanya, supaya query
            // "strategi apa saja yang ada" tidak pernah kehilangan baris diam-diam.
            $label = $this->classify($trade->notes ?? '') ?? 'manual_discretionary';
            $counts[$label] = ($counts[$label] ?? 0) + 1;
            if (! $dryRun) {
                $trade->update(['strategy_label' => $label]);
            }
        }

        foreach ($counts as $label => $n) {
            $this->line("{$label}: {$n} trade".($dryRun ? ' (dry-run, tidak disimpan)' : ''));
        }
        $this->info('Total diproses: '.array_sum($counts));

        return self::SUCCESS;
    }

    private function classify(string $notes): ?string
    {
        foreach (self::PATTERNS as $label => $needles) {
            foreach ($needles as $needle) {
                if (str_contains($notes, $needle)) {
                    return $label;
                }
            }
        }

        return null;
    }
}
