<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use App\Services\Sentiment\SentimentEngineManager;
use Illuminate\Console\Command;

class ReanalyzeSentimentCommand extends Command
{
    protected $signature = 'sentiment:reanalyze {--stock= : Stock code, omit for all} {--limit=50 : Articles per stock} {--force : Re-analyze even if already has ml_sentiment_label}';

    protected $description = 'Re-run sentiment analysis for existing articles using configured engine (hybrid/IndoBERT + rule)';

    public function handle(SentimentEngineManager $engineManager): int
    {
        $analyzer = $engineManager->getAnalyzer();
        $baselineAnalyzer = new RuleBasedSentimentAnalyzer();
        $code = strtoupper($this->option('stock') ?: '');
        $limit = (int) $this->option('limit');
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
            $query = NewsArticle::where('stock_id', $stock->id)->orderByDesc('published_at');
            if (! $force) {
                $query->whereNull('ml_sentiment_label');
            }
            if ($limit > 0) {
                $query->limit($limit);
            }

            $articles = $query->get();
            $count = $articles->count();
            if ($count === 0) {
                $this->line("{$stock->code}: no articles to process");
                continue;
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
                    'stock_code' => $stock->code,
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

            $totals['processed'] += $processed;
            $totals['ml'] += $mlUsed;
            $totals['fallback'] += $fallback;
            $totals['agree'] += $agree;
            $totals['disagree'] += $disagree;

            $this->line("{$stock->code}: processed={$processed} ml={$mlUsed} fallback={$fallback} agree={$agree} disagree={$disagree}");
        }

        $agreementRate = $totals['ml'] > 0 ? round(($totals['agree'] / $totals['ml']) * 100, 1) : 0;
        $mlRate = $totals['processed'] > 0 ? round(($totals['ml'] / $totals['processed']) * 100, 1) : 0;

        $this->info("Total: {$totals['processed']} articles | ML: {$totals['ml']} ({$mlRate}%) | Agreement: {$agreementRate}% ({$totals['agree']}/{$totals['ml']})");

        return self::SUCCESS;
    }
}
