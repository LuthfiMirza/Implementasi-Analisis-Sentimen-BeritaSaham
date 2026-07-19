<?php

namespace App\Console\Commands;

use App\Models\SentimentManualLabel;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;

class ExportSentimentFinetuneDatasetCommand extends Command
{
    protected $signature = 'sentiment:export-finetune-dataset
        {--output-dir=storage/app/sentiment_finetune : Output directory for train/val/test JSONL}
        {--train-ratio=0.7}
        {--val-ratio=0.15}
        {--seed=42}';

    protected $description = 'Export sentiment_manual_labels joined with article text (production-matching format) for IndoBERT fine-tuning, stratified train/val/test split';

    public function handle(): int
    {
        $outputDir = base_path((string) $this->option('output-dir'));
        $trainRatio = (float) $this->option('train-ratio');
        $valRatio = (float) $this->option('val-ratio');
        $seed = (int) $this->option('seed');

        if (! is_dir($outputDir)) {
            mkdir($outputDir, 0777, true);
        }

        $rows = SentimentManualLabel::with('article')->get()
            ->filter(fn (SentimentManualLabel $row) => $row->article !== null)
            ->map(function (SentimentManualLabel $row) {
                return [
                    'news_article_id' => $row->news_article_id,
                    'text' => $this->buildProductionInputText($row->article),
                    'label' => $row->label,
                    'ml_sentiment_label' => $row->article->ml_sentiment_label,
                    'rule_sentiment_label' => $row->article->rule_sentiment_label,
                ];
            })
            ->filter(fn (array $row) => trim($row['text']) !== '')
            ->values();

        $this->info(sprintf('Loaded %d labeled rows with non-empty text.', $rows->count()));

        $splits = $this->stratifiedSplit($rows, $trainRatio, $valRatio, $seed);

        foreach ($splits as $name => $splitRows) {
            $path = $outputDir.DIRECTORY_SEPARATOR.$name.'.jsonl';
            $this->writeJsonl($path, $splitRows);
            $this->info(sprintf('%s: %d rows -> %s', $name, $splitRows->count(), $path));
            $this->line('  label distribution: '.$splitRows->countBy('label')->map(fn ($c, $l) => "$l=$c")->implode(', '));
        }

        return self::SUCCESS;
    }

    /**
     * Replicates PythonApiSentimentAnalyzer::analyze() input construction exactly,
     * so the fine-tuning training distribution matches production serving distribution.
     */
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
