<?php

namespace App\Console\Commands;

use App\Models\SentimentManualLabel;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;

/**
 * Fase R7d: exports the subset of sentiment_manual_labels whose article now has full_text
 * (Fase R7a backfill), building two text variants from the SAME rows/split so the comparison
 * isolates input construction only: title_summary (identical formula to production) and
 * title_summary_fulltext (production formula + full_text appended). Separate from
 * ExportSentimentFinetuneDatasetCommand (the production dataset exporter) to avoid touching
 * that command for a one-off research ablation.
 */
class ExportR7dFulltextAblationCommand extends Command
{
    protected $signature = 'sentiment:export-r7d-fulltext-ablation
        {--output-dir=data/evaluation/r7d_fulltext_ablation}
        {--train-ratio=0.7}
        {--val-ratio=0.15}
        {--seed=42}';

    protected $description = 'Export title_summary vs title_summary_fulltext variants (same rows/split) for the R7d full_text ablation';

    public function handle(): int
    {
        $outputDir = base_path((string) $this->option('output-dir'));
        $trainRatio = (float) $this->option('train-ratio');
        $valRatio = (float) $this->option('val-ratio');
        $seed = (int) $this->option('seed');

        $rows = SentimentManualLabel::with('article')
            ->get()
            ->filter(fn (SentimentManualLabel $row) => $row->article !== null && trim((string) $row->article->full_text) !== '')
            ->map(fn (SentimentManualLabel $row) => [
                'news_article_id' => $row->news_article_id,
                'text_title_summary' => $this->buildProductionInputText($row->article),
                'text_title_summary_fulltext' => $this->buildFulltextInputText($row->article),
                'label' => $row->label,
                'source_provider' => $row->article->source_provider,
            ])
            ->filter(fn (array $row) => $row['text_title_summary'] !== '' && $row['text_title_summary_fulltext'] !== '')
            ->values();

        $this->info(sprintf('Loaded %d labeled rows with non-empty full_text.', $rows->count()));
        $this->line('Label distribution: '.$rows->countBy('label')->map(fn ($c, $l) => "$l=$c")->implode(', '));

        $splits = $this->stratifiedSplit($rows, $trainRatio, $valRatio, $seed);

        foreach (['title_summary', 'title_summary_fulltext'] as $variant) {
            $variantDir = $outputDir.DIRECTORY_SEPARATOR.$variant;
            if (! is_dir($variantDir)) {
                mkdir($variantDir, 0777, true);
            }

            foreach ($splits as $name => $splitRows) {
                $path = $variantDir.DIRECTORY_SEPARATOR.$name.'.jsonl';
                $mapped = $splitRows->map(fn (array $row) => [
                    'news_article_id' => $row['news_article_id'],
                    'text' => $variant === 'title_summary' ? $row['text_title_summary'] : $row['text_title_summary_fulltext'],
                    'label' => $row['label'],
                ]);
                $this->writeJsonl($path, $mapped);
                $this->info(sprintf('%s/%s: %d rows -> %s', $variant, $name, $mapped->count(), $path));
                $this->line('  label distribution: '.$mapped->countBy('label')->map(fn ($c, $l) => "$l=$c")->implode(', '));
            }
        }

        return self::SUCCESS;
    }

    /** Identical to ExportSentimentFinetuneDatasetCommand::buildProductionInputText() -- must match production exactly. */
    protected function buildProductionInputText($article): string
    {
        $text = $article->summary ?? $article->content_snippet ?? $article->title;

        $inputText = trim(implode('. ', array_filter([
            $article->title,
            $article->summary,
            strlen((string) $text) < 200 ? $text : null,
        ])));

        if ($inputText === '') {
            $inputText = (string) $text;
        }

        return mb_substr($inputText, 0, 512);
    }

    protected function buildFulltextInputText($article): string
    {
        $inputText = trim(implode('. ', array_filter([
            $article->title,
            $article->summary,
            $article->full_text,
        ])));

        return mb_substr($inputText, 0, 4000);
    }

    protected function stratifiedSplit(Collection $rows, float $trainRatio, float $valRatio, int $seed): array
    {
        $train = collect();
        $val = collect();
        $test = collect();

        foreach ($rows->groupBy('label') as $labelRows) {
            $shuffled = $labelRows->values()->shuffle($seed);
            $count = $shuffled->count();
            $trainEnd = (int) round($count * $trainRatio);
            $valEnd = $trainEnd + (int) round($count * $valRatio);

            $train = $train->concat($shuffled->slice(0, $trainEnd));
            $val = $val->concat($shuffled->slice($trainEnd, $valEnd - $trainEnd));
            $test = $test->concat($shuffled->slice($valEnd));
        }

        return [
            'train' => $train->shuffle($seed)->values(),
            'val' => $val->shuffle($seed)->values(),
            'test' => $test->shuffle($seed)->values(),
        ];
    }

    protected function writeJsonl(string $path, Collection $rows): void
    {
        $handle = fopen($path, 'wb');
        if ($handle === false) {
            throw new \RuntimeException('Unable to open for writing: '.$path);
        }

        foreach ($rows as $row) {
            fwrite($handle, json_encode($row, JSON_UNESCAPED_UNICODE).PHP_EOL);
        }

        fclose($handle);
    }
}
