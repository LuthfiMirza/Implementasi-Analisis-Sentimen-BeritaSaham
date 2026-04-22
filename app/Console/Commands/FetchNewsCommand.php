<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('news:fetch {--limit=20} {--stock=} {--provider=} {--debug}')]
#[Description('Ambil berita terbaru untuk semua saham aktif atau 1 saham')]
class FetchNewsCommand extends Command
{
    protected const FETCH_RESULT_JSON_PREFIX = 'FETCH_RESULT_JSON:';

    /**
     * Execute the console command.
     */
    public function handle(NewsAggregationService $newsAggregationService)
    {
        $limit = (int) $this->option('limit');
        $single = $this->option('stock');
        $providerOverride = $this->option('provider') ? [$this->option('provider')] : null;
        $stocks = $single
            ? Stock::where('code', strtoupper($single))->get()
            : Stock::where('is_active', true)->get();

        $provider = $providerOverride[0] ?? config('services.news.provider', env('NEWS_PROVIDER', 'mock'));
        $errors = 0;
        $aggregate = [
            'stocks' => 0,
            'raw' => 0,
            'saved' => 0,
            'updated' => 0,
            'dropped_relevance' => 0,
            'dropped_quality' => 0,
            'dropped_language' => 0,
            'dropped_exclusion' => 0,
            'dropped_irrelevant' => 0,
            'skipped_dedup' => 0,
            'by_provider' => [],
            'kept_score_sum' => 0.0,
            'kept_score_count' => 0,
            'drop_score_sum' => 0.0,
            'drop_score_count' => 0,
            'band_high' => 0,
            'band_medium' => 0,
            'band_low' => 0,
        ];

        foreach ($stocks as $stock) {
            try {
                $before = microtime(true);
                $stats = $newsAggregationService->refreshFromProvider($stock, $limit, $providerOverride);
                $duration = round(microtime(true) - $before, 3);

                $aggregate['stocks']++;
                foreach ($aggregate as $k => $v) {
                    if (isset($stats[$k]) && is_int($stats[$k])) {
                        $aggregate[$k] += $stats[$k];
                    }
                }
                foreach ($stats['by_provider'] as $prov => $count) {
                    $aggregate['by_provider'][$prov] = ($aggregate['by_provider'][$prov] ?? 0) + $count;
                }
                $aggregate['kept_score_sum'] += $stats['kept_score_sum'] ?? 0;
                $aggregate['kept_score_count'] += $stats['kept_score_count'] ?? 0;
                $aggregate['drop_score_sum'] += $stats['drop_score_sum'] ?? 0;
                $aggregate['drop_score_count'] += $stats['drop_score_count'] ?? 0;
                $aggregate['band_high'] += $stats['band_high'] ?? 0;
                $aggregate['band_medium'] += $stats['band_medium'] ?? 0;
                $aggregate['band_low'] += $stats['band_low'] ?? 0;
                $aggregate['drop_relevance_sum'] = ($aggregate['drop_relevance_sum'] ?? 0) + ($stats['drop_relevance_sum'] ?? 0);
                $aggregate['drop_entity_sum'] = ($aggregate['drop_entity_sum'] ?? 0) + ($stats['drop_entity_sum'] ?? 0);
                $aggregate['drop_market_sum'] = ($aggregate['drop_market_sum'] ?? 0) + ($stats['drop_market_sum'] ?? 0);
                $aggregate['kept_relevance_sum'] = ($aggregate['kept_relevance_sum'] ?? 0) + ($stats['kept_relevance_sum'] ?? 0);
                $aggregate['kept_entity_sum'] = ($aggregate['kept_entity_sum'] ?? 0) + ($stats['kept_entity_sum'] ?? 0);
                $aggregate['kept_market_sum'] = ($aggregate['kept_market_sum'] ?? 0) + ($stats['kept_market_sum'] ?? 0);

                $this->info("{$stock->code}: raw {$stats['raw']}, saved {$stats['saved']}, updated {$stats['updated']}, dropped (rel/lang/qual/excl/dup) {$stats['dropped_relevance']}/{$stats['dropped_language']}/{$stats['dropped_quality']}/{$stats['dropped_exclusion']}/{$stats['skipped_dedup']}, waktu {$duration}s");
                if ($this->option('debug')) {
                    $this->line(self::FETCH_RESULT_JSON_PREFIX.json_encode([
                        'ticker' => $stock->code,
                        'provider' => $provider,
                        'raw' => (int) ($stats['raw'] ?? 0),
                        'saved' => (int) ($stats['saved'] ?? 0),
                        'updated' => (int) ($stats['updated'] ?? 0),
                        'dropped_relevance' => (int) ($stats['dropped_relevance'] ?? 0),
                        'dropped_quality' => (int) ($stats['dropped_quality'] ?? 0),
                        'dropped_exclusion' => (int) ($stats['dropped_exclusion'] ?? 0),
                        'skipped_dedup' => (int) ($stats['skipped_dedup'] ?? 0),
                        'failed' => (int) ($stats['failed'] ?? 0),
                        'dropped_samples' => $stats['dropped_samples'] ?? [
                            'relevance' => [],
                            'quality' => [],
                            'exclusion' => [],
                        ],
                    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
                }
                if ($this->option('debug')) {
                    $avgKeep = ($stats['kept_score_count'] ?? 0) > 0 ? round($stats['kept_score_sum'] / $stats['kept_score_count'], 3) : '-';
                    $avgDrop = ($stats['drop_score_count'] ?? 0) > 0 ? round($stats['drop_score_sum'] / $stats['drop_score_count'], 3) : '-';
                    $this->line('  provider: '.json_encode($stats['by_provider']));
                    $this->line("  avg keep {$avgKeep}, avg drop {$avgDrop}, band H/M/L {$stats['band_high']}/{$stats['band_medium']}/{$stats['band_low']}");
                    $avgRelDrop = ($stats['dropped_relevance'] ?? 0) > 0 ? round(($stats['drop_relevance_sum'] ?? 0) / $stats['dropped_relevance'], 3) : '-';
                    $avgEntDrop = ($stats['dropped_relevance'] ?? 0) > 0 ? round(($stats['drop_entity_sum'] ?? 0) / $stats['dropped_relevance'], 3) : '-';
                    $avgMktDrop = ($stats['dropped_relevance'] ?? 0) > 0 ? round(($stats['drop_market_sum'] ?? 0) / $stats['dropped_relevance'], 3) : '-';
                    $this->line("  dropped (relevance) avg rel/entity/market: {$avgRelDrop}/{$avgEntDrop}/{$avgMktDrop}");
                    if (!empty(array_filter($stats['dropped_samples'] ?? []))) {
                        $this->line('  sample dropped: '.json_encode($stats['dropped_samples']));
                    }
                }
            } catch (\Throwable $e) {
                $errors++;
                $this->error("Gagal fetch {$stock->code}: ".$e->getMessage());
                if ($this->option('debug')) {
                    $this->line(self::FETCH_RESULT_JSON_PREFIX.json_encode([
                        'ticker' => $stock->code,
                        'provider' => $provider,
                        'raw' => 0,
                        'saved' => 0,
                        'updated' => 0,
                        'dropped_relevance' => 0,
                        'dropped_quality' => 0,
                        'dropped_exclusion' => 0,
                        'skipped_dedup' => 0,
                        'failed' => 1,
                        'dropped_samples' => [
                            'relevance' => [],
                            'quality' => [],
                            'exclusion' => [],
                        ],
                    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
                }
                \Log::error('news:fetch error', ['stock' => $stock->code, 'error' => $e->getMessage()]);
                continue;
            }
        }

        $this->line("Summary: stok diproses {$aggregate['stocks']}, raw {$aggregate['raw']}, saved {$aggregate['saved']}, updated {$aggregate['updated']}, error {$errors}, provider {$provider}");
        $avgKeep = $aggregate['kept_score_count'] > 0 ? round($aggregate['kept_score_sum'] / $aggregate['kept_score_count'], 3) : '-';
        $avgDrop = $aggregate['drop_score_count'] > 0 ? round($aggregate['drop_score_sum'] / $aggregate['drop_score_count'], 3) : '-';
        $avgRelDrop = ($aggregate['dropped_relevance'] ?? 0) > 0 ? round(($aggregate['drop_relevance_sum'] ?? 0) / $aggregate['dropped_relevance'], 3) : '-';
        $avgEntDrop = ($aggregate['dropped_relevance'] ?? 0) > 0 ? round(($aggregate['drop_entity_sum'] ?? 0) / $aggregate['dropped_relevance'], 3) : '-';
        $avgMktDrop = ($aggregate['dropped_relevance'] ?? 0) > 0 ? round(($aggregate['drop_market_sum'] ?? 0) / $aggregate['dropped_relevance'], 3) : '-';
        $this->line("Average final score keep/drop: {$avgKeep} / {$avgDrop} | Band H/M/L: {$aggregate['band_high']}/{$aggregate['band_medium']}/{$aggregate['band_low']}");
        $this->line("Average dropped (relevance) rel/entity/market: {$avgRelDrop}/{$avgEntDrop}/{$avgMktDrop}");
        $this->line('Provider breakdown:');
        foreach ($aggregate['by_provider'] as $prov => $count) {
            $this->line("- {$prov}: {$count}");
        }
    }
}
