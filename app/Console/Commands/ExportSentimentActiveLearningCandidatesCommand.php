<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use Illuminate\Console\Command;
use Illuminate\Database\Eloquent\Builder;

class ExportSentimentActiveLearningCandidatesCommand extends Command
{
    protected $signature = 'sentiment:export-active-learning-candidates
        {--output=storage/app/sentiment_finetune/active_learning_positive_candidates.csv : CSV output path}
        {--limit=200 : Maximum rows to export}
        {--positive-threshold=0.35 : Minimum ML positive probability for candidate rows}
        {--uncertain-margin=0.15 : Maximum top-vs-positive probability gap for uncertain rows}';

    protected $description = 'Export unlabeled positive-leaning sentiment candidates for human active-learning labels';

    public function handle(): int
    {
        $output = base_path((string) $this->option('output'));
        $limit = max(1, (int) $this->option('limit'));
        $positiveThreshold = (float) $this->option('positive-threshold');
        $uncertainMargin = (float) $this->option('uncertain-margin');

        $rows = NewsArticle::query()
            ->with('stock')
            ->whereDoesntHave('manualLabels')
            ->whereNotNull('ml_prob_positive')
            ->where(function (Builder $query) use ($positiveThreshold, $uncertainMargin): void {
                $query->where('ml_sentiment_label', 'positive')
                    ->orWhere('rule_sentiment_label', 'positive')
                    ->orWhere('ml_prob_positive', '>=', $positiveThreshold)
                    ->orWhereRaw($this->topProbabilitySql().' - COALESCE(ml_prob_positive, 0) <= ?', [$uncertainMargin]);
            })
            ->orderByDesc('ml_prob_positive')
            ->orderByDesc('published_at')
            ->limit($limit)
            ->get()
            ->map(fn (NewsArticle $article): array => $this->row($article));

        if (! is_dir(dirname($output))) {
            mkdir(dirname($output), 0777, true);
        }

        $handle = fopen($output, 'wb');
        if ($handle === false) {
            $this->error('Unable to write '.$output);

            return self::FAILURE;
        }

        fputcsv($handle, array_keys($rows->first() ?? $this->emptyRow()));
        foreach ($rows as $row) {
            fputcsv($handle, $row);
        }
        fclose($handle);

        $this->info(sprintf('Exported %d candidates -> %s', $rows->count(), $output));
        $this->warn('Human label required. Do not treat candidate score as ground truth.');

        return self::SUCCESS;
    }

    private function row(NewsArticle $article): array
    {
        return [
            'news_article_id' => $article->id,
            'published_at' => optional($article->published_at)->toDateString(),
            'stock' => $article->stock?->code,
            'source' => $article->source_provider,
            'title' => $article->title,
            'summary' => $article->summary ?? $article->content_snippet,
            'ml_label' => $article->ml_sentiment_label,
            'rule_label' => $article->rule_sentiment_label,
            'ml_prob_positive' => $article->ml_prob_positive,
            'ml_prob_neutral' => $article->ml_prob_neutral,
            'ml_prob_negative' => $article->ml_prob_negative,
            'source_url' => $article->source_url,
            'human_label' => '',
        ];
    }

    private function emptyRow(): array
    {
        return [
            'news_article_id' => '',
            'published_at' => '',
            'stock' => '',
            'source' => '',
            'title' => '',
            'summary' => '',
            'ml_label' => '',
            'rule_label' => '',
            'ml_prob_positive' => '',
            'ml_prob_neutral' => '',
            'ml_prob_negative' => '',
            'source_url' => '',
            'human_label' => '',
        ];
    }

    private function topProbabilitySql(): string
    {
        return <<<'SQL'
(CASE
    WHEN COALESCE(ml_prob_positive, 0) >= COALESCE(ml_prob_neutral, 0)
        AND COALESCE(ml_prob_positive, 0) >= COALESCE(ml_prob_negative, 0)
        THEN COALESCE(ml_prob_positive, 0)
    WHEN COALESCE(ml_prob_neutral, 0) >= COALESCE(ml_prob_negative, 0)
        THEN COALESCE(ml_prob_neutral, 0)
    ELSE COALESCE(ml_prob_negative, 0)
END)
SQL;
    }
}
