<?php

namespace App\Console\Commands;

use App\Models\SentimentManualLabel;
use App\Services\Sentiment\NewsArticleTypeClassifier;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

class AuditSentimentManualLabelsCommand extends Command
{
    protected $signature = 'sentiment:audit-manual-labels
        {--confidence=0.85 : Minimum production ML confidence/probability for a mismatch to be flagged}
        {--csv=output/prediction_research/sentiment_label_audit_report.csv : CSV output path}
        {--txt=output/prediction_research/sentiment_label_audit_report.txt : Text summary output path}';

    protected $description = 'Flag manual sentiment labels that disagree with high-confidence production model predictions';

    public function handle(NewsArticleTypeClassifier $classifier): int
    {
        $threshold = (float) $this->option('confidence');
        $rows = SentimentManualLabel::with(['article.stock', 'user'])->get();
        $flagged = [];

        foreach ($rows as $label) {
            $article = $label->article;
            if (! $article || ! $article->ml_sentiment_label) {
                continue;
            }

            $confidence = $this->confidenceFor($article->ml_sentiment_label, $article);
            if ($confidence < $threshold || $article->ml_sentiment_label === $label->label) {
                continue;
            }

            $flagged[] = [
                'manual_label_id' => $label->id,
                'news_article_id' => $article->id,
                'sample_method' => $label->sample_method,
                'article_type' => $classifier->classify($article),
                'stock' => $article->stock?->code,
                'published_at' => optional($article->published_at)->toDateString(),
                'manual_label' => $label->label,
                'ml_label' => $article->ml_sentiment_label,
                'ml_confidence' => round($confidence, 4),
                'rule_label' => $article->rule_sentiment_label,
                'title' => $article->title,
                'summary' => $article->summary ?? $article->content_snippet,
                'source_url' => $article->source_url,
                'review_decision' => '',
            ];
        }

        usort($flagged, fn (array $left, array $right): int => $right['ml_confidence'] <=> $left['ml_confidence']);
        $this->writeCsv(base_path((string) $this->option('csv')), $flagged);
        $this->writeTextReport(base_path((string) $this->option('txt')), $rows->count(), $flagged, $threshold);

        $this->info(sprintf('Audited %d labels, flagged %d high-confidence mismatches.', $rows->count(), count($flagged)));

        return self::SUCCESS;
    }

    private function confidenceFor(string $label, $article): float
    {
        return match ($label) {
            'positive' => (float) ($article->ml_prob_positive ?? $article->ml_confidence ?? $article->ml_sentiment_score ?? 0),
            'neutral' => (float) ($article->ml_prob_neutral ?? $article->ml_confidence ?? $article->ml_sentiment_score ?? 0),
            'negative' => (float) ($article->ml_prob_negative ?? $article->ml_confidence ?? abs((float) ($article->ml_sentiment_score ?? 0))),
            default => (float) ($article->ml_confidence ?? 0),
        };
    }

    private function writeCsv(string $path, array $rows): void
    {
        File::ensureDirectoryExists(dirname($path));
        $handle = fopen($path, 'wb');
        $header = array_keys($rows[0] ?? [
            'manual_label_id' => '', 'news_article_id' => '', 'sample_method' => '', 'article_type' => '',
            'stock' => '', 'published_at' => '', 'manual_label' => '', 'ml_label' => '', 'ml_confidence' => '',
            'rule_label' => '', 'title' => '', 'summary' => '', 'source_url' => '', 'review_decision' => '',
        ]);
        fputcsv($handle, $header);
        foreach ($rows as $row) {
            fputcsv($handle, $row);
        }
        fclose($handle);
    }

    private function writeTextReport(string $path, int $total, array $flagged, float $threshold): void
    {
        File::ensureDirectoryExists(dirname($path));
        $byType = collect($flagged)->countBy('article_type');
        $byPair = collect($flagged)->countBy(fn (array $row): string => $row['manual_label'].'→'.$row['ml_label']);
        $lines = [
            'Sentiment Manual Label Audit',
            '============================',
            '',
            'Rule: flag manual labels that disagree with high-confidence production ML predictions.',
            sprintf('Confidence threshold: %.2f', $threshold),
            sprintf('Manual labels audited: %d', $total),
            sprintf('Flagged for human re-review: %d', count($flagged)),
            '',
            'By article type:',
        ];
        foreach ($byType as $type => $count) {
            $lines[] = sprintf('  %s: %d', $type, $count);
        }
        $lines[] = '';
        $lines[] = 'By manual→ML mismatch:';
        foreach ($byPair as $pair => $count) {
            $lines[] = sprintf('  %s: %d', $pair, $count);
        }
        $lines[] = '';
        $lines[] = 'No labels were changed automatically.';
        file_put_contents($path, implode(PHP_EOL, $lines).PHP_EOL);
    }
}
