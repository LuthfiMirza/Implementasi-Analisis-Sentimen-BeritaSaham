<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\Analytics\EvaluationReportService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Storage;

class GenerateEvaluationReport extends Command
{
    protected $signature = 'evaluate:report {code=BBCA} {--period=30} {--output=} {--no-macro : Exclude global macro news such as OJK} {--macro-regulatory-signal= : Override macro regulatory signal with 1 or 0}';

    protected $description = 'Hasilkan ringkasan evaluasi sentimen, analytics, dan prediksi untuk satu saham';

    public function handle(EvaluationReportService $service): int
    {
        $code = strtoupper($this->argument('code'));
        $period = (int) $this->option('period');
        $macroOption = $this->option('macro-regulatory-signal');
        $macroRegulatorySignal = $macroOption === null
            ? null
            : filter_var($macroOption, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);

        if ($macroOption !== null && $macroRegulatorySignal === null) {
            $this->error('Nilai --macro-regulatory-signal harus 1/0 atau true/false.');

            return self::FAILURE;
        }

        $stock = Stock::where('code', $code)->first();
        if (! $stock) {
            $this->error("Saham {$code} tidak ditemukan.");
            return self::FAILURE;
        }

        $report = $service->generate(
            $stock,
            $period,
            ! $this->option('no-macro'),
            $macroRegulatorySignal
        );

        $this->info("Evaluasi {$code} ({$period} hari)");
        $this->line(json_encode($report, JSON_PRETTY_PRINT));

        $output = $this->option('output');
        if ($output) {
            $path = "evaluations/{$output}";
            Storage::put($path, json_encode($report, JSON_PRETTY_PRINT));
            $this->info("Tersimpan ke storage/app/{$path}");
        }

        return self::SUCCESS;
    }
}
