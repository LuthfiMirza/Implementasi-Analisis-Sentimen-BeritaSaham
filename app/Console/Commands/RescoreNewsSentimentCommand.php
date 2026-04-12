<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\News\SentimentAnalysisService;
use Illuminate\Console\Command;

class RescoreNewsSentimentCommand extends Command
{
    protected $signature = 'news:rescore-sentiment';

    protected $description = 'Rescore sentiment for all news articles';

    public function handle(SentimentAnalysisService $service): int
    {
        $total = 0;
        $changed = 0;

        NewsArticle::chunk(100, function ($articles) use ($service, &$total, &$changed) {
            foreach ($articles as $article) {
                $old = $article->sentiment_label;
                $service->analyzeAndUpdate($article);
                $article->refresh();
                if ($article->sentiment_label !== $old) {
                    $changed++;
                }
                $total++;
            }
        });

        $this->info("Total: {$total} Changed: {$changed}");
        $counts = NewsArticle::selectRaw('sentiment_label, count(*) as c')
            ->groupBy('sentiment_label')
            ->pluck('c', 'sentiment_label');
        foreach ($counts as $label => $count) {
            $this->line("{$label}: {$count}");
        }

        return self::SUCCESS;
    }
}
