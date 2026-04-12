<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Sentiment\HybridSentimentAnalyzer;
use App\Services\Sentiment\PythonApiSentimentAnalyzer;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use Illuminate\Console\Command;

class ReanalyzeSentimentCommand extends Command
{
    protected $signature = 'sentiment:reanalyze {--stock=} {--limit=50} {--method=hybrid}';

    protected $description = 'Re-run sentiment analysis for existing articles with selected engine';

    public function handle(): int
    {
        $method = strtolower($this->option('method') ?? 'hybrid');
        $analyzer = match ($method) {
            'python' => new PythonApiSentimentAnalyzer(new RuleBasedSentimentAnalyzer()),
            'rule_based' => new RuleBasedSentimentAnalyzer(),
            default => new HybridSentimentAnalyzer(
                new PythonApiSentimentAnalyzer(new RuleBasedSentimentAnalyzer()),
                new RuleBasedSentimentAnalyzer()
            ),
        };

        $query = NewsArticle::query()->orderByDesc('published_at');

        if ($code = $this->option('stock')) {
            $stock = Stock::where('code', strtoupper($code))->first();
            if (! $stock) {
                $this->error("Stock {$code} not found.");
                return Command::FAILURE;
            }
            $query->where('stock_id', $stock->id);
        }

        $limit = (int) $this->option('limit');
        if ($limit > 0) {
            $query->limit($limit);
        }

        $articles = $query->get();
        $total = 0;
        $mlTotal = 0;
        $agree = 0;

        foreach ($articles as $article) {
            $result = $analyzer->analyze(
                $article->summary ?? $article->content_snippet ?? $article->title,
                [
                    'title' => $article->title,
                    'summary' => $article->summary,
                    'body' => $article->full_text ?? $article->content_snippet,
                    'language' => $article->language ?? 'id',
                ]
            );

            $article->sentiment_label = $result['label'] ?? $article->sentiment_label;
            $article->sentiment_score = $result['score'] ?? $article->sentiment_score;
            $article->sentiment_confidence = $result['confidence'] ?? $article->sentiment_confidence;
            $article->sentiment_method = $result['method'] ?? $article->sentiment_method ?? $method;
            $article->sentiment_meta = [
                'matched_positive_terms' => $result['matched_positive_terms'] ?? [],
                'matched_negative_terms' => $result['matched_negative_terms'] ?? [],
                'reason_summary' => $result['reason_summary'] ?? null,
            ];
            $article->analyzed_at = now();

            $article->ml_sentiment_label = $result['ml_label'] ?? ($result['method'] === 'python' ? ($result['label'] ?? null) : $article->ml_sentiment_label);
            $article->ml_sentiment_score = $result['ml_score'] ?? ($result['method'] === 'python' ? ($result['score'] ?? null) : $article->ml_sentiment_score);
            $article->ml_confidence = $result['ml_confidence'] ?? ($result['method'] === 'python' ? ($result['confidence'] ?? null) : $article->ml_confidence);
            $article->rule_sentiment_label = $result['rule_label'] ?? ($result['method'] !== 'python' ? ($result['label'] ?? null) : $article->rule_sentiment_label);
            $article->rule_sentiment_score = $result['rule_score'] ?? ($result['method'] !== 'python' ? ($result['score'] ?? null) : $article->rule_sentiment_score);

            if ($article->ml_sentiment_label && $article->rule_sentiment_label) {
                $article->ml_rule_agree = $article->ml_sentiment_label === $article->rule_sentiment_label;
            }

            $article->save();

            $total++;
            if ($article->ml_sentiment_label) {
                $mlTotal++;
                if ($article->ml_rule_agree) {
                    $agree++;
                }
            }
        }

        $this->info("Processed: {$total} articles");
        if ($mlTotal > 0) {
            $rate = round(($agree / $mlTotal) * 100, 1);
            $this->info("ML vs Rule agreement: {$rate}% ({$agree}/{$mlTotal})");
        } else {
            $this->info('No ML sentiments generated.');
        }

        return Command::SUCCESS;
    }
}
