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
        {--seed=42}
        {--sample-method=* : Include only these sample_method values; use null for NULL}
        {--exclude-sample-method=* : Exclude these sample_method values; use null for NULL}';

    protected $description = 'Export sentiment_manual_labels joined with article text (production-matching format) for IndoBERT fine-tuning, stratified train/val/test split';

    public function handle(): int
    {
        $outputDir = base_path((string) $this->option('output-dir'));
        $trainRatio = (float) $this->option('train-ratio');
        $valRatio = (float) $this->option('val-ratio');
        $seed = (int) $this->option('seed');
        $sampleMethods = collect((array) $this->option('sample-method'))->filter()->values();
        $excludeSampleMethods = collect((array) $this->option('exclude-sample-method'))->filter()->values();

        if (! is_dir($outputDir)) {
            mkdir($outputDir, 0777, true);
        }

        $query = SentimentManualLabel::with('article');

        if ($sampleMethods->isNotEmpty()) {
            $query->where(function ($query) use ($sampleMethods) {
                $values = $sampleMethods->reject(fn ($value) => $value === 'null')->all();
                if ($values) {
                    $query->whereIn('sample_method', $values);
                }
                if ($sampleMethods->contains('null')) {
                    $values ? $query->orWhereNull('sample_method') : $query->whereNull('sample_method');
                }
            });
        }

        if ($excludeSampleMethods->isNotEmpty()) {
            $values = $excludeSampleMethods->reject(fn ($value) => $value === 'null')->all();
            if ($values) {
                $query->whereNotIn('sample_method', $values);
            }
            if ($excludeSampleMethods->contains('null')) {
                $query->whereNotNull('sample_method');
            }
        }

        $rows = $query->get()
            ->filter(fn (SentimentManualLabel $row) => $row->article !== null)
            ->map(function (SentimentManualLabel $row) {
                return [
                    'news_article_id' => $row->news_article_id,
                    'text' => $this->buildProductionInputText($row->article),
                    'label' => $row->label,
                    'sample_method' => $row->sample_method,
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
