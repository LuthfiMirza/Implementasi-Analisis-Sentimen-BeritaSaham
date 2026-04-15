<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\Analytics\SentimentComparisonService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Storage;

class SentimentComparisonCommand extends Command
{
    protected $signature = 'evaluation:sentiment-compare {code?} {--period=30} {--save=} {--no-macro : Exclude global macro news such as OJK}';

    protected $description = 'Bandingkan weighted vs average sentiment (korelasi, event, sinyal arah) untuk saham tertentu';

    public function handle(SentimentComparisonService $service): int
    {
        $code = $this->argument('code') ?? config('dashboard.default_stock', 'BBCA');
        $period = (int) $this->option('period');

        $stock = Stock::where('code', $code)->first();
        if (! $stock) {
            $this->error("Saham {$code} tidak ditemukan.");
            return self::FAILURE;
        }

        $report = $service->evaluate($stock, $period, ! $this->option('no-macro'));

        $this->info("Evaluasi sentiment vs weighted ({$code}, {$period} hari)");
        $this->line(json_encode($report, JSON_PRETTY_PRINT));

        if ($path = $this->option('save')) {
            $file = 'evaluations/'.$path;
            Storage::put($file, json_encode($report, JSON_PRETTY_PRINT));
            $this->info("Tersimpan: storage/app/{$file}");
        }

        return self::SUCCESS;
    }
}
