<?php

namespace App\Console\Commands;

use App\Models\FetchLog;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:fetch {--limit=5}')]
#[Description('Ambil berita terbaru untuk semua saham aktif')]
class FetchNewsCommand extends Command
{
    /**
     * Execute the console command.
     */
    public function handle(NewsAggregationService $newsAggregationService)
    {
        $limit = (int) $this->option('limit');
        $stocks = Stock::where('is_active', true)->get();

        foreach ($stocks as $stock) {
            $newsAggregationService->refreshFromProvider($stock, $limit);
            $this->info("Berita {$stock->code} diperbarui.");
        }

        FetchLog::create([
            'source_name' => config('services.news.provider', 'mock'),
            'status' => 'success',
            'message' => 'Fetch via command',
            'records_count' => $stocks->count() * $limit,
            'ran_at' => Carbon::now(),
        ]);
    }
}
