<?php

namespace App\Console\Commands;

use App\Models\FetchLog;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:fetch {--limit=20} {--stock=}')]
#[Description('Ambil berita terbaru untuk semua saham aktif atau 1 saham')]
class FetchNewsCommand extends Command
{
    /**
     * Execute the console command.
     */
    public function handle(NewsAggregationService $newsAggregationService)
    {
        $limit = (int) $this->option('limit');
        $single = $this->option('stock');
        $stocks = $single
            ? Stock::where('code', strtoupper($single))->get()
            : Stock::where('is_active', true)->get();

        $fetched = 0;
        $errors = 0;
        $provider = config('services.news.provider', env('NEWS_PROVIDER', 'mock'));

        foreach ($stocks as $stock) {
            try {
                $before = now();
                $newsAggregationService->refreshFromProvider($stock, $limit);
                $this->info("Berita {$stock->code} diperbarui (waktu: ".now()->diffInSeconds($before)."s).");
                $fetched += $limit;
            } catch (\Throwable $e) {
                $errors++;
                $this->error("Gagal fetch {$stock->code}: ".$e->getMessage());
                \Log::error('news:fetch error', ['stock' => $stock->code, 'error' => $e->getMessage()]);
                continue;
            }
        }

        FetchLog::create([
            'source_name' => $provider,
            'status' => $errors ? 'partial' : 'success',
            'message' => 'Fetch via command',
            'records_count' => $fetched,
            'ran_at' => Carbon::now(),
        ]);

        $this->line("Summary: stok diproses {$stocks->count()}, fetched target ~{$fetched}, error {$errors}, provider {$provider}");
    }
}
