<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\Sentiment\SentimentEngineManager;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:analyze {--all : proses ulang semua artikel}')]
#[Description('Analisis sentimen artikel berita dengan rule-based analyzer')]
class AnalyzeSentimentCommand extends Command
{
    /**
     * Execute the console command.
     */
    public function handle()
    {
        $analyzer = (new SentimentEngineManager())->getAnalyzer();
        $query = NewsArticle::query();

        if (! $this->option('all')) {
            $query->whereNull('sentiment_label');
        }

        $count = 0;
        $failed = 0;
        foreach ($query->cursor() as $article) {
            try {
                $result = $analyzer->analyze(
                    $article->summary ?? $article->content_snippet ?? $article->title,
                    [
                        'title' => $article->title,
                        'summary' => $article->summary,
                        'body' => $article->full_text ?? $article->content_snippet,
                        'language' => $article->language ?? 'id',
                    ]
                );
                $article->update([
                    'sentiment_label' => $result['label'],
                    'sentiment_score' => $result['score'],
                    'sentiment_confidence' => $result['confidence'] ?? null,
                    'sentiment_method' => $result['method'] ?? 'python_unavailable',
                    'sentiment_meta' => [
                        'matched_positive_terms' => $result['matched_positive_terms'] ?? [],
                        'matched_negative_terms' => $result['matched_negative_terms'] ?? [],
                        'reason_summary' => $result['reason_summary'] ?? null,
                        'python_status' => $result['python_status'] ?? null,
                    ],
                    'analyzed_at' => now(),
                ]);
                $count++;
            } catch (\Throwable $e) {
                $failed++;
                $this->error("Gagal analisis ID {$article->id}: ".$e->getMessage());
                \Log::error('news:analyze error', ['id' => $article->id, 'error' => $e->getMessage()]);
                continue;
            }
        }

        $this->info("Analisis selesai. Berhasil: {$count}, gagal: {$failed}");
    }
}
