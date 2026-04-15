<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\RelevanceScoringService;
use App\Services\News\StockKeywordMapper;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class RescoreNewsQualityCommand extends Command
{
    protected $signature = 'news:rescore-quality
        {--stock= : Kode saham (opsional)}
        {--days=180 : Rentang hari ke belakang}
        {--force : Paksa rescore semua artikel pada rentang ini}
        {--limit= : Batasi jumlah artikel yang diproses}';

    protected $description = 'Backfill metadata kualitas berita (relevance/quality/provider) untuk artikel yang belum lengkap';

    public function handle(): int
    {
        $days = (int) $this->option('days');
        $stockCode = $this->option('stock');
        $force = (bool) $this->option('force');
        $limit = $this->option('limit') ? (int) $this->option('limit') : null;

        $mapper = new StockKeywordMapper();
        $scorer = new RelevanceScoringService($mapper);

        $query = NewsArticle::query()
            ->with('stock')
            ->when($days > 0, fn ($q) => $q->whereDate('published_at', '>=', Carbon::now()->subDays($days - 1)))
            ->when($stockCode, function ($q) use ($stockCode) {
                $stock = Stock::where('code', strtoupper($stockCode))->first();
                if ($stock) {
                    $q->where('stock_id', $stock->id);
                } else {
                    $this->error("Saham {$stockCode} tidak ditemukan");
                }
            })
            ->when(! $force, function ($q) {
                $q->where(function ($qq) {
                    $qq->whereNull('final_quality_score')
                        ->orWhereNull('quality_band')
                        ->orWhereNull('relevance_score')
                        ->orWhereNull('source_provider');
                });
            })
            ->orderByDesc('published_at');

        if ($limit) {
            $query->limit($limit);
        }

        $total = 0;
        $updated = 0;
        $skipped = 0;
        $failed = 0;

        foreach ($query->cursor() as $article) {
            $total++;
            try {
                $stock = $article->stock;
                if (! $stock) {
                    $skipped++;
                    continue;
                }

                $raw = [
                    'title' => $article->title,
                    'summary' => $article->summary,
                    'content_snippet' => $article->content_snippet,
                    'full_text' => $article->full_text,
                    'source_url' => $article->source_url,
                    'language' => $article->language,
                    'detected_language' => $article->detected_language,
                    'provider' => $article->source_provider ?: ($article->raw_payload['provider'] ?? null),
                ];

                $score = $scorer->score($stock, $raw, $raw['provider']);
                $overwrite = $force;
                $article->forceFill([
                    'source_provider' => ($overwrite || ! $article->source_provider) ? ($raw['provider'] ?: 'unknown') : $article->source_provider,
                    'relevance_score' => ($overwrite || $article->relevance_score === null) ? $score['relevance_score'] : $article->relevance_score,
                    'relevance_band' => ($overwrite || ! $article->relevance_band) ? $score['relevance_band'] : $article->relevance_band,
                    'entity_match_score' => ($overwrite || $article->entity_match_score === null) ? $score['entity_match_score'] : $article->entity_match_score,
                    'market_context_score' => ($overwrite || $article->market_context_score === null) ? $score['market_context_score'] : $article->market_context_score,
                    'language_score' => ($overwrite || $article->language_score === null) ? $score['language_score'] : $article->language_score,
                    'final_quality_score' => ($overwrite || $article->final_quality_score === null) ? $score['final_quality_score'] : $article->final_quality_score,
                    'quality_band' => ($overwrite || ! $article->quality_band) ? $score['quality_band'] : $article->quality_band,
                    'quality_flags' => ($overwrite || empty($article->quality_flags)) ? $score['quality_flags'] : $article->quality_flags,
                    'matched_keywords' => ($overwrite || empty($article->matched_keywords)) ? $score['matched_keywords'] : $article->matched_keywords,
                    'detected_language' => ($overwrite || ! $article->detected_language) ? $score['detected_language'] : $article->detected_language,
                ])->save();

                $updated++;
            } catch (\Throwable $e) {
                $failed++;
                Log::error('news:rescore-quality error', [
                    'article_id' => $article->id,
                    'error' => $e->getMessage(),
                ]);
                $this->error("Gagal rescore artikel {$article->id}: ".$e->getMessage());
            }
        }

        $this->info("Rescore selesai. Total: {$total}, updated: {$updated}, skipped: {$skipped}, failed: {$failed}");

        return self::SUCCESS;
    }
}
