<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\StockKeywordMapper;
use Illuminate\Console\Command;

/**
 * Re-checks articles linked to common-word ticker codes (BUMI, DEWA) against the
 * fixed word-boundary/case-sensitive keyword matching in StockKeywordMapper. Any
 * article that no longer matches under the fixed rule is unlinked (stock_id set
 * to null) instead of deleted, so it stops polluting that stock's sentiment
 * aggregation while remaining auditable.
 */
class CleanupKeywordMismatchCommand extends Command
{
    protected $signature = 'news:cleanup-keyword-mismatches {--codes=BUMI,DEWA} {--force : Actually unlink mismatches; without this flag, only reports what would change}';

    protected $description = 'Unlink news articles that were false-positive matched to a stock via common-word/substring keyword collisions';

    public function handle(StockKeywordMapper $mapper): int
    {
        $codes = array_filter(array_map('trim', explode(',', (string) $this->option('codes'))));
        $force = (bool) $this->option('force');

        $totalMismatches = 0;

        foreach ($codes as $code) {
            $stock = Stock::where('code', strtoupper($code))->first();
            if (! $stock) {
                $this->warn("Stock not found: {$code}");
                continue;
            }

            $articles = NewsArticle::where('stock_id', $stock->id)->get();
            $mismatches = [];

            foreach ($articles as $article) {
                $text = trim($article->title.' '.$article->summary);
                $hits = $mapper->directHits($stock, $text);
                if (empty($hits)) {
                    $mismatches[] = $article;
                }
            }

            $totalMismatches += count($mismatches);
            $this->line("{$code}: {$articles->count()} total, ".count($mismatches)." mismatch under fixed keyword rule");

            foreach ($mismatches as $article) {
                $this->line("  - [{$article->id}] {$article->title}");
                if ($force) {
                    $article->update(['stock_id' => null]);
                }
            }
        }

        if (! $force && $totalMismatches > 0) {
            $this->newLine();
            $this->comment('Dry-run only. Re-run with --force to unlink these articles from their stock.');
        }

        return self::SUCCESS;
    }
}
