<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Storage;

class NewsCoverageReportCommand extends Command
{
    protected $signature = 'news:coverage-report
        {--stock= : Kode saham tunggal, mis. BBCA}
        {--days=30 : Rentang hari ke belakang}
        {--save= : Simpan laporan ke file (JSON) di storage/app}
    ';

    protected $description = 'Laporan coverage berita per saham (jumlah artikel, kualitas, provider, kelayakan evaluasi)';

    public function handle(): int
    {
        $days = (int) $this->option('days');
        $stockCode = $this->option('stock');
        $save = $this->option('save');

        $fromDate = Carbon::now()->subDays(max(0, $days - 1));

        $query = NewsArticle::with('stock')
            ->whereDate('published_at', '>=', $fromDate->toDateString());

        if ($stockCode) {
            $stock = Stock::where('code', $stockCode)->first();
            if (! $stock) {
                $this->error("Saham {$stockCode} tidak ditemukan");
                return self::FAILURE;
            }
            $query->where('stock_id', $stock->id);
        }

        $articles = $query->get();
        if ($articles->isEmpty()) {
            $this->warn('Tidak ada artikel pada rentang ini.');
            return self::SUCCESS;
        }

        $perStock = $articles->groupBy(fn ($a) => $a->stock?->code ?? 'GEN')->map(
            fn (Collection $items, $code) => $this->summarizeStock($code, $items)
        );

        $aggregate = $this->summarizeAggregate($articles);

        $this->table(
            ['Saham', 'Artikel', 'Hari Ada Sentimen', 'Q:High/Med/Low', 'Sentimen P/N/Z', 'Eval Ready'],
            $perStock->values()->map(function ($row) {
                return [
                    $row['stock_code'],
                    $row['article_count'],
                    $row['days_with_sentiment'],
                    "{$row['high_quality_count']}/{$row['medium_quality_count']}/{$row['low_quality_count']}",
                    "{$row['positive_count']}/{$row['neutral_count']}/{$row['negative_count']}",
                    $row['evaluation_ready'] ? 'Ya' : 'Tidak',
                ];
            })->toArray()
        );

        $this->info('Ringkasan provider (total/high-quality/missingQuality):');
        foreach ($aggregate['providers'] as $prov => $data) {
            $this->line("- {$prov}: {$data['total']} / {$data['high_quality']} high (missing quality: {$data['missing_quality']})");
        }

        if ($save) {
            $payload = [
                'generated_at' => now()->toIso8601String(),
                'range_days' => $days,
                'stocks' => array_values($perStock->toArray()),
                'aggregate' => $aggregate,
            ];
            Storage::put($save, json_encode($payload, JSON_PRETTY_PRINT));
            $this->info("Laporan disimpan ke storage/app/{$save}");
        }

        return self::SUCCESS;
    }

    protected function summarizeStock(string $code, Collection $items): array
    {
        $articleCount = $items->count();
        $daysWithArticles = $items->pluck('published_at')->filter()->map(fn ($d) => Carbon::parse($d)->toDateString())->unique()->count();
        $daysWithSentiment = $items->filter(fn ($a) => $a->sentiment_label)->pluck('published_at')->map(fn ($d) => Carbon::parse($d)->toDateString())->unique()->count();

        $qualityCounts = [
            'high' => $items->where('quality_band', 'high')->count(),
            'medium' => $items->where('quality_band', 'medium')->count(),
            'low' => $items->where('quality_band', 'low')->count(),
        ];

        $sentimentCounts = [
            'positive' => $items->where('sentiment_label', 'positive')->count(),
            'neutral' => $items->where('sentiment_label', 'neutral')->count(),
            'negative' => $items->where('sentiment_label', 'negative')->count(),
        ];

        $avgRelevance = round((float) $items->avg('relevance_score'), 3);
        $avgQuality = round((float) $items->avg('final_quality_score'), 3);

        $providers = $items->groupBy(fn ($a) => $a->source_provider ?: 'unknown')->map(fn ($c) => [
            'total' => $c->count(),
            'high_quality' => $c->where('quality_band', 'high')->count(),
            'missing_quality' => $c->whereNull('quality_band')->count(),
        ])->sortByDesc('total')->toArray();

        $evaluationReady = $articleCount >= 15 && $daysWithSentiment >= 10;
        $reason = $evaluationReady ? 'Cukup artikel & hari sentimen' : 'Artikel/hari sentimen belum cukup';

        return [
            'stock_code' => $code,
            'article_count' => $articleCount,
            'days_with_articles' => $daysWithArticles,
            'days_with_sentiment' => $daysWithSentiment,
            'positive_count' => $sentimentCounts['positive'],
            'neutral_count' => $sentimentCounts['neutral'],
            'negative_count' => $sentimentCounts['negative'],
            'high_quality_count' => $qualityCounts['high'],
            'medium_quality_count' => $qualityCounts['medium'],
            'low_quality_count' => $qualityCounts['low'],
            'avg_relevance_score' => $avgRelevance,
            'avg_final_quality_score' => $avgQuality,
            'providers' => $providers,
            'evaluation_ready' => $evaluationReady,
            'evaluation_reason' => $reason,
        ];
    }

    protected function summarizeAggregate(Collection $items): array
    {
        $providers = $items->groupBy(fn ($a) => $a->source_provider ?: 'unknown')->map(fn ($c) => [
            'total' => $c->count(),
            'high_quality' => $c->where('quality_band', 'high')->count(),
            'missing_quality' => $c->whereNull('quality_band')->count(),
        ])->sortByDesc('total')->toArray();

        $byStock = $items->groupBy(fn ($a) => $a->stock?->code ?? 'GEN')->map->count();
        $lowest = $byStock->sort()->take(3);
        $highest = $byStock->sortDesc()->take(3);

        return [
            'providers' => $providers,
            'lowest_stocks' => $lowest,
            'highest_stocks' => $highest,
        ];
    }
}
