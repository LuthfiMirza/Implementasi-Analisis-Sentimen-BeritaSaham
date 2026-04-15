<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\Analytics\EvaluationReportService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Storage;

class GenerateEvaluationReport extends Command
{
    protected $signature = 'evaluate:report {code=BBCA} {--period=30} {--output=} {--no-macro : Exclude global macro news such as OJK}';

    protected $description = 'Hasilkan ringkasan evaluasi sentimen, analytics, dan prediksi untuk satu saham';

    public function handle(EvaluationReportService $service): int
    {
        $code = strtoupper($this->argument('code'));
        $period = (int) $this->option('period');

        $stock = Stock::where('code', $code)->first();
        if (! $stock) {
            $this->error("Saham {$code} tidak ditemukan.");
            return self::FAILURE;
        }

        $report = $service->generate($stock, $period, ! $this->option('no-macro'));

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
