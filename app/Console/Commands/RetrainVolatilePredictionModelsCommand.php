<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;
use Symfony\Component\Process\Process;

class RetrainVolatilePredictionModelsCommand extends Command
{
    protected $signature = 'prediction:retrain-volatile {--dry-run : Show planned retrain without executing} {--force : Retrain even when no new data exists}';

    protected $description = 'Safely retrain BUMI/DEWA volatile-stock prediction artifacts with backup, candidate gating, and JSONL history.';

    protected const VARIANTS = [
        'bumi_technical' => [
            'ticker' => 'BUMI',
            'artifact' => 'model_bumi_technical.joblib',
            'metadata' => 'model_bumi_technical_metadata.json',
        ],
        'dewa_regime' => [
            'ticker' => 'DEWA',
            'artifact' => 'model_dewa_regime.joblib',
            'metadata' => 'model_dewa_regime_metadata.json',
        ],
        'dewa_technical' => [
            'ticker' => 'DEWA',
            'artifact' => 'model_dewa_technical.joblib',
            'metadata' => 'model_dewa_technical_metadata.json',
        ],
    ];

    public function handle(): int
    {
        $predictionDir = env('PREDICTION_RETRAIN_MODEL_DIR', storage_path('app/prediction'));
        $historyPath = $predictionDir.'/retrain_history.jsonl';
        $timestamp = now('Asia/Jakarta');
        $force = (bool) $this->option('force');
        $dryRun = (bool) $this->option('dry-run');
        $plans = $this->buildPlans($predictionDir, $timestamp);
        $shouldRetrain = $force || collect($plans)->contains(fn (array $plan): bool => $plan['has_new_data']);

        foreach ($plans as $variant => $plan) {
            $this->line(sprintf(
                '%s: latest_data=%s trained_at=%s new_prices=%d new_articles=%d decision=%s',
                $variant,
                $plan['latest_data_at'] ?? 'n/a',
                $plan['trained_at'] ?? 'n/a',
                $plan['new_price_rows'],
                $plan['new_article_rows'],
                $shouldRetrain ? ($dryRun ? 'would_retrain' : 'retrain') : 'skip_no_new_data'
            ));
        }

        if (! $shouldRetrain) {
            foreach ($plans as $variant => $plan) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'skip', $plan, null, null, 'no new data, skip'));
            }
            $this->info('No new data since last training; skipped retrain. Use --force to override.');

            return self::SUCCESS;
        }

        if ($dryRun) {
            foreach ($plans as $variant => $plan) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'dry_run', $plan, null, null, 'dry run only; no artifact changed'));
            }
            $this->info('Dry run complete; no models were retrained.');

            return self::SUCCESS;
        }

        $candidateDir = $predictionDir.'/candidates/retrain_'.$timestamp->format('Ymd_His');
        File::ensureDirectoryExists($candidateDir);

        $script = base_path(env('PREDICTION_VOLATILE_TRAIN_SCRIPT', 'quant/train_volatile_stock_models.py'));
        $python = env('PYTHON_BINARY', 'python3');
        $process = new Process([$python, $script, '--output-dir', $candidateDir], base_path(), null, null, 600);
        $process->run(function (string $type, string $buffer): void {
            $this->output->write($buffer);
        });

        if (! $process->isSuccessful()) {
            $this->error('Retrain script failed. Candidate directory preserved: '.$candidateDir);
            foreach ($plans as $variant => $plan) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'failed', $plan, null, null, trim($process->getErrorOutput() ?: $process->getOutput())));
            }

            return self::FAILURE;
        }

        $archiveDir = $predictionDir.'/archive';
        File::ensureDirectoryExists($archiveDir);
        $suffix = $timestamp->format('Ymd_His');

        foreach (self::VARIANTS as $variant => $spec) {
            $plan = $plans[$variant];
            $oldMetadataPath = $predictionDir.'/'.$spec['metadata'];
            $newMetadataPath = $candidateDir.'/'.$spec['metadata'];
            $newArtifactPath = $candidateDir.'/'.$spec['artifact'];
            $oldMetrics = $this->metricsFromMetadata($this->readJson($oldMetadataPath));
            $newMetadata = $this->readJson($newMetadataPath);
            $newMetrics = $this->metricsFromMetadata($newMetadata);

            if (! File::exists($newMetadataPath) || ! File::exists($newArtifactPath)) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'failed', $plan, $oldMetrics, $newMetrics, 'candidate artifact missing'));
                $this->warn($variant.': candidate artifact missing; production unchanged.');
                continue;
            }

            $macroDelta = ($newMetrics['macro_f1'] ?? 0.0) - ($oldMetrics['macro_f1'] ?? 0.0);
            if ($macroDelta < -0.05) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'candidate', $plan, $oldMetrics, $newMetrics, 'macro F1 dropped more than 0.05; production unchanged', $candidateDir));
                $this->warn(sprintf('%s: candidate kept, production unchanged (macro F1 delta %.4f).', $variant, $macroDelta));
                continue;
            }

            foreach (['artifact', 'metadata'] as $kind) {
                $productionPath = $predictionDir.'/'.$spec[$kind];
                if (File::exists($productionPath)) {
                    File::copy($productionPath, $archiveDir.'/'.pathinfo($spec[$kind], PATHINFO_FILENAME).'_'.$suffix.'.'.pathinfo($spec[$kind], PATHINFO_EXTENSION));
                }
                File::copy($candidateDir.'/'.$spec[$kind], $productionPath);
            }

            $this->appendHistory($historyPath, $this->historyRow($variant, 'replace', $plan, $oldMetrics, $newMetrics, 'candidate accepted and production replaced', $candidateDir));
            $this->info(sprintf('%s: replaced production (macro F1 old %.4f -> new %.4f).', $variant, $oldMetrics['macro_f1'] ?? 0.0, $newMetrics['macro_f1'] ?? 0.0));
        }

        return self::SUCCESS;
    }

    protected function buildPlans(string $predictionDir, Carbon $now): array
    {
        $plans = [];
        foreach (self::VARIANTS as $variant => $spec) {
            $metadata = $this->readJson($predictionDir.'/'.$spec['metadata']);
            $trainedAt = $this->parseDate($metadata['trained_at'] ?? null);
            $ticker = $spec['ticker'];
            $stock = Stock::where('code', $ticker)->first();
            $latestPriceAt = $stock
                ? StockPrice::where('stock_id', $stock->id)->where('interval_type', '1d')->max('price_date')
                : null;
            $latestArticleAt = $stock
                ? NewsArticle::where('stock_id', $stock->id)->whereNotNull('published_at')->max('published_at')
                : null;
            $latestDataAt = collect([$this->parseDate($latestPriceAt), $this->parseDate($latestArticleAt)])->filter()->max();
            $newPriceRows = $stock && $trainedAt
                ? StockPrice::where('stock_id', $stock->id)->where('interval_type', '1d')->where('price_date', '>', $trainedAt)->count()
                : 0;
            $newArticleRows = $stock && $trainedAt
                ? NewsArticle::where('stock_id', $stock->id)->whereNotNull('published_at')->where('published_at', '>', $trainedAt)->count()
                : 0;

            $plans[$variant] = [
                'ticker' => $ticker,
                'trained_at' => $trainedAt?->toIso8601String(),
                'latest_data_at' => $latestDataAt instanceof Carbon ? $latestDataAt->toIso8601String() : null,
                'new_price_rows' => $newPriceRows,
                'new_article_rows' => $newArticleRows,
                'has_new_data' => $trainedAt === null || $newPriceRows > 0 || $newArticleRows > 0,
                'checked_at' => $now->toIso8601String(),
            ];
        }

        return $plans;
    }

    protected function metricsFromMetadata(array $metadata): array
    {
        $summary = is_array($metadata['research_summary'] ?? null) ? $metadata['research_summary'] : [];
        return [
            'macro_f1' => isset($summary['macro_f1']) ? (float) $summary['macro_f1'] : null,
            'directional_accuracy' => isset($summary['directional_accuracy']) ? (float) $summary['directional_accuracy'] : null,
        ];
    }

    protected function historyRow(string $variant, string $decision, array $plan, ?array $oldMetrics, ?array $newMetrics, string $message, ?string $candidateDir = null): array
    {
        return [
            'timestamp' => now('Asia/Jakarta')->toIso8601String(),
            'model' => $variant,
            'ticker' => $plan['ticker'],
            'decision' => $decision,
            'old_metrics' => $oldMetrics,
            'new_metrics' => $newMetrics,
            'new_price_rows' => $plan['new_price_rows'],
            'new_article_rows' => $plan['new_article_rows'],
            'trained_at_before' => $plan['trained_at'],
            'latest_data_at' => $plan['latest_data_at'],
            'candidate_dir' => $candidateDir,
            'message' => $message,
        ];
    }

    protected function appendHistory(string $path, array $row): void
    {
        File::ensureDirectoryExists(dirname($path));
        File::append($path, json_encode($row, JSON_UNESCAPED_SLASHES).PHP_EOL);
    }

    protected function readJson(string $path): array
    {
        if (! File::exists($path)) {
            return [];
        }

        $decoded = json_decode((string) File::get($path), true);
        return is_array($decoded) ? $decoded : [];
    }

    protected function parseDate(mixed $value): ?Carbon
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            return Carbon::parse($value, 'Asia/Jakarta');
        } catch (\Throwable) {
            return null;
        }
    }
}
