<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use App\Services\Sentiment\SentimentEngineManager;
use Illuminate\Console\Command;

class ReanalyzeSentimentCommand extends Command
{
    protected $signature = 'sentiment:reanalyze
        {--stock= : Stock code, omit for all}
        {--limit=0 : Articles per stock, 0 means no limit}
        {--include-global : Include articles without stock_id such as market/OJK news}
        {--force : Re-analyze even if sentiment labels already exist}';

    protected $description = 'Re-run sentiment analysis for existing articles using configured engine (hybrid/IndoBERT + rule)';

    public function handle(SentimentEngineManager $engineManager): int
    {
        $analyzer = $engineManager->getAnalyzer();
        $baselineAnalyzer = new RuleBasedSentimentAnalyzer();
        $code = strtoupper($this->option('stock') ?: '');
        $limit = (int) $this->option('limit');
        $includeGlobal = (bool) $this->option('include-global');
        $force = (bool) $this->option('force');

        $stocksQuery = Stock::query()->where('is_active', true);
        if ($code) {
            $stocksQuery->where('code', $code);
        }
        $stocks = $stocksQuery->get();

        if ($stocks->isEmpty()) {
            $this->error('No stocks found for re-analysis.');
            return self::FAILURE;
        }

        $totals = [
            'processed' => 0,
            'ml' => 0,
            'fallback' => 0,
            'agree' => 0,
            'disagree' => 0,
        ];

        foreach ($stocks as $stock) {
            $stockTotals = $this->processArticles(
                NewsArticle::where('stock_id', $stock->id),
                $stock->code,
                $limit,
                $force,
                $analyzer,
                $baselineAnalyzer
            );

            foreach ($totals as $key => $value) {
                $totals[$key] += $stockTotals[$key];
            }
        }

        if ($includeGlobal && ! $code) {
            $globalTotals = $this->processArticles(
                NewsArticle::whereNull('stock_id'),
                'GLOBAL',
                0,
                $force,
                $analyzer,
                $baselineAnalyzer
            );

            foreach ($totals as $key => $value) {
                $totals[$key] += $globalTotals[$key];
            }
        }

        $agreementRate = $totals['ml'] > 0 ? round(($totals['agree'] / $totals['ml']) * 100, 1) : 0;
        $mlRate = $totals['processed'] > 0 ? round(($totals['ml'] / $totals['processed']) * 100, 1) : 0;

        $this->info("Total: {$totals['processed']} articles | ML: {$totals['ml']} ({$mlRate}%) | Agreement: {$agreementRate}% ({$totals['agree']}/{$totals['ml']})");

        return self::SUCCESS;
    }

    protected function processArticles($query, string $scope, int $limit, bool $force, $analyzer, RuleBasedSentimentAnalyzer $baselineAnalyzer): array
    {
        $query->orderByDesc('published_at');

        if (! $force) {
            $query->where(function ($query) {
                $query->whereNull('sentiment_label')
                    ->orWhereNull('ml_sentiment_label')
                    ->orWhereNull('rule_sentiment_label');
            });
        }

        if ($limit > 0) {
            $query->limit($limit);
        }

        $articles = $query->get();
        $count = $articles->count();
        if ($count === 0) {
            $this->line("{$scope}: no articles to process");
            return ['processed' => 0, 'ml' => 0, 'fallback' => 0, 'agree' => 0, 'disagree' => 0];
        }

        $bar = $this->output->createProgressBar($count);
        $bar->start();

        $processed = $mlUsed = $fallback = $agree = $disagree = 0;

        foreach ($articles as $article) {
            $text = $article->summary ?? $article->content_snippet ?? $article->title;
            $context = [
                'title' => $article->title,
                'summary' => $article->summary,
                'body' => $article->full_text ?? $article->content_snippet,
                'language' => $article->language ?? 'id',
                'stock_code' => $article->stock?->code,
            ];

            $analysis = $analyzer->analyze($text, $context);
            $baseline = $baselineAnalyzer->analyze($text, $context);

            $article->sentiment_label = $analysis['label'] ?? $article->sentiment_label;
            $article->sentiment_score = $analysis['score'] ?? $article->sentiment_score;
            $article->sentiment_confidence = $analysis['confidence'] ?? $article->sentiment_confidence;
            $article->sentiment_method = $analysis['method'] ?? $article->sentiment_method ?? 'rule_based';
            $article->sentiment_meta = [
                'matched_positive_terms' => $analysis['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $analysis['matched_negative_terms'] ?? [],
                'reason_summary' => $analysis['reason_summary'] ?? null,
                'python_status' => $analysis['python_status'] ?? null,
            ];

            $article->ml_sentiment_label = $analysis['ml_label'] ?? $article->ml_sentiment_label;
            $article->ml_sentiment_score = $analysis['ml_score'] ?? $article->ml_sentiment_score;
            $article->ml_confidence = $analysis['ml_confidence'] ?? $article->ml_confidence;
            $article->ml_prob_positive = $analysis['ml_prob_positive'] ?? $article->ml_prob_positive;
            $article->ml_prob_neutral = $analysis['ml_prob_neutral'] ?? $article->ml_prob_neutral;
            $article->ml_prob_negative = $analysis['ml_prob_negative'] ?? $article->ml_prob_negative;
            $article->rule_sentiment_label = $analysis['rule_label'] ?? $baseline['label'] ?? $article->rule_sentiment_label;
            $article->rule_sentiment_score = $analysis['rule_score'] ?? $baseline['score'] ?? $article->rule_sentiment_score;
            $article->ml_rule_agree = isset($article->ml_sentiment_label, $article->rule_sentiment_label)
                ? $article->ml_sentiment_label === $article->rule_sentiment_label
                : $article->ml_rule_agree;
            $article->analyzed_at = now();

            $article->save();

            $processed++;
            $isMl = ($analysis['method'] ?? '') === 'python';
            $isAgree = $article->ml_rule_agree === true;

            $isMl ? $mlUsed++ : $fallback++;
            $isAgree ? $agree++ : ($isAgree === false ? $disagree++ : null);

            $bar->advance();
        }

        $bar->finish();
        $this->newLine();
        $this->line("{$scope}: processed={$processed} ml={$mlUsed} fallback={$fallback} agree={$agree} disagree={$disagree}");

        return [
            'processed' => $processed,
            'ml' => $mlUsed,
            'fallback' => $fallback,
            'agree' => $agree,
            'disagree' => $disagree,
        ];
    }
}
