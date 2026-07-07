<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use Illuminate\Console\Command;

/**
 * Retroactively applies the rule-based tiebreak (see SentimentAnalysisService) to already-stored
 * articles where ml_sentiment_label and rule_sentiment_label disagree. These were persisted before
 * the tiebreak fix, so sentiment_label still reflects the old "always trust ML" behavior. No API
 * calls needed: both labels are already stored, this just flips the final label using data on hand.
 */
class ApplyRuleBasedTiebreakCommand extends Command
{
    protected $signature = 'news:apply-rule-tiebreak {--force : Actually update rows; without this flag, only reports what would change}';

    protected $description = 'Retroactively set sentiment_label to rule_sentiment_label for stored articles where ML and rule-based disagree';

    public function handle(): int
    {
        $force = (bool) $this->option('force');

        $query = NewsArticle::where('ml_rule_agree', false)
            ->whereNotNull('rule_sentiment_label')
            ->where('sentiment_method', '!=', 'rule_based_tiebreak');

        $total = $query->count();
        $this->line("{$total} artikel disagreement belum pakai tiebreak rule-based.");

        if ($total === 0) {
            return self::SUCCESS;
        }

        if (! $force) {
            $sample = (clone $query)->limit(5)->get(['id', 'title', 'sentiment_label', 'rule_sentiment_label']);
            foreach ($sample as $article) {
                $this->line("  - [{$article->id}] {$article->sentiment_label} -> {$article->rule_sentiment_label} | {$article->title}");
            }
            $this->comment('Dry-run only. Re-run with --force to apply.');

            return self::SUCCESS;
        }

        $updated = 0;
        $query->chunkById(200, function ($articles) use (&$updated) {
            foreach ($articles as $article) {
                $article->forceFill([
                    'sentiment_label' => $article->rule_sentiment_label,
                    'sentiment_score' => $article->rule_sentiment_score ?? $article->sentiment_score,
                    'sentiment_method' => 'rule_based_tiebreak',
                ])->save();
                $updated++;
            }
        });

        $this->info("Updated {$updated} articles.");

        return self::SUCCESS;
    }
}
