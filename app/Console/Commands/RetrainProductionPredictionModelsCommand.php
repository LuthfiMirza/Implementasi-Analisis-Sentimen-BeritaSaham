<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Log;
use Symfony\Component\Process\Process;

/**
 * Safely retrains the V6A (technical-only) / V6B (technical+sentiment) production models for the
 * 10 official tickers, mirroring RetrainVolatilePredictionModelsCommand's safety pattern (candidate
 * gating, backup+promote, JSONL history) that was already proven for BUMI/DEWA. Before this command
 * existed, these models were frozen since 2026-06-21/22 with no retrain schedule at all -- see
 * plan.md for the audit that found this.
 *
 * Unlike the volatile system, gating here compares `retrain_evaluation.macro_f1` (a walk-forward
 * OOS metric computed FRESH every run by train_production_models.py) rather than a frozen
 * `official_baseline` constant -- that constant never changes between retrains, so comparing against
 * it would never actually detect degradation.
 */
class RetrainProductionPredictionModelsCommand extends Command
{
    protected $signature = 'prediction:retrain-production
        {--dry-run : Show planned retrain without executing}
        {--force : Retrain even when no new data exists}
        {--variant= : Optional model variant: technical, technical_sentiment}';

    protected $description = 'Safely retrain V6A/V6B production prediction models with fresh walk-forward evaluation, candidate gating, and JSONL history.';

    protected const DEGRADATION_THRESHOLD = 0.05;

    protected const OFFICIAL_TICKERS = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'GOTO', 'INDF', 'ICBP', 'ADRO', 'UNVR'];

    protected const VARIANTS = [
        'technical' => [
            'artifact' => 'model_technical_v6a.joblib',
            'metadata' => 'model_technical_v6a_metadata.json',
        ],
        'technical_sentiment' => [
            'artifact' => 'model_technical_sentiment_v6b.joblib',
            'metadata' => 'model_technical_sentiment_v6b_metadata.json',
        ],
    ];

    public function handle(): int
    {
        $selectedVariant = $this->selectedVariant();
        if ($selectedVariant === false) {
            return self::FAILURE;
        }

        $predictionDir = env('PREDICTION_RETRAIN_MODEL_DIR', storage_path('app/prediction'));
        $historyPath = $predictionDir.'/retrain_history.jsonl';
        $timestamp = now('Asia/Jakarta');
        $force = (bool) $this->option('force');
        $dryRun = (bool) $this->option('dry-run');
        $variants = $selectedVariant ? [$selectedVariant => self::VARIANTS[$selectedVariant]] : self::VARIANTS;
        $plans = $this->buildPlans($predictionDir, $variants);

        foreach ($plans as $variant => $plan) {
            $willRetrain = $force || $plan['has_new_data'];
            $this->line(sprintf(
                '%s: trained_at=%s rows_new_data=%d decision=%s',
                $variant,
                $plan['trained_at'] ?? 'n/a (never trained with this pipeline)',
                $plan['rows_new_data'],
                $willRetrain ? ($dryRun ? 'would_retrain' : 'retrain') : 'skip_no_new_data'
            ));
        }

        if ($dryRun) {
            $this->info('Dry run complete; no Python process was called and no artifact was changed.');

            return self::SUCCESS;
        }

        $anyRetrain = $force || collect($plans)->contains('has_new_data', true);
        if (! $anyRetrain) {
            foreach ($plans as $variant => $plan) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'skipped', $plan, null, null, $force));
            }
            $this->info('No new data across all requested variants, skip. Use --force to retrain anyway.');

            return self::SUCCESS;
        }

        // Relative to base_path() (env-overridable so tests don't overwrite the real production
        // dataset CSVs, which train_production_models.py reads from the canonical
        // output/prediction_research/ path via its hardcoded MODEL_SPECS).
        $datasetRelDir = env('PREDICTION_RETRAIN_DATASET_DIR', 'output/prediction_research');

        $this->info('Regenerating research dataset for the 10 official tickers...');
        $exportExit = Artisan::call('prediction:export-research-dataset', [
            '--ticker' => self::OFFICIAL_TICKERS,
            '--output' => $datasetRelDir.'/dataset_v6_retrain.csv',
            '--per-ticker-dir' => $datasetRelDir.'/tickers_v6_retrain',
        ]);
        if ($exportExit !== 0) {
            $this->error('prediction:export-research-dataset failed; aborting retrain.');

            return self::FAILURE;
        }

        // Both V6A/V6B are structurally the same feature set (V6B is a superset), so one fresh
        // export is copied to both filenames rather than exporting twice.
        $datasetAbsDir = base_path($datasetRelDir);
        File::copy($datasetAbsDir.'/dataset_v6_retrain.csv', $datasetAbsDir.'/dataset_v6a.csv');
        File::copy($datasetAbsDir.'/dataset_v6_retrain.csv', $datasetAbsDir.'/dataset_v6b_10ticker.csv');

        $candidateDir = $predictionDir.'/candidates/retrain_'.$timestamp->format('Ymd_His');
        File::ensureDirectoryExists($candidateDir);

        $variantArg = $selectedVariant ?? 'all';
        $process = $this->runTrainingProcess($variantArg, $candidateDir);
        if (! $process->isSuccessful()) {
            $this->error('train_production_models.py failed. Candidate directory preserved: '.$candidateDir);
            Log::warning('Production model retrain failed', [
                'variant' => $variantArg,
                'output' => trim($process->getErrorOutput() ?: $process->getOutput()),
            ]);

            return self::FAILURE;
        }

        $exitCode = self::SUCCESS;
        foreach ($variants as $variant => $spec) {
            $plan = $plans[$variant];
            if (! $force && ! $plan['has_new_data']) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'skipped', $plan, null, null, $force));
                continue;
            }

            $oldMetadataPath = $predictionDir.'/'.$spec['metadata'];
            $newMetadataPath = $candidateDir.'/'.$spec['metadata'];
            $newArtifactPath = $candidateDir.'/'.$spec['artifact'];

            if (! File::exists($newMetadataPath) || ! File::exists($newArtifactPath)) {
                $this->warn($variant.': candidate artifact missing; production unchanged.');
                Log::warning('Production model candidate artifact missing', ['variant' => $variant, 'candidate_dir' => $candidateDir]);
                $exitCode = self::FAILURE;
                continue;
            }

            $oldMetrics = $this->retrainEvalFromMetadata($this->readJson($oldMetadataPath));
            $newMetrics = $this->retrainEvalFromMetadata($this->readJson($newMetadataPath));

            if ($oldMetrics['macro_f1'] === null) {
                // No prior retrain_evaluation to compare against (e.g. first run of this command,
                // or production metadata predates this field) -- promote unconditionally, there is
                // no baseline to protect against regressing from.
                $this->promote($predictionDir, $candidateDir, $spec, $variant, $timestamp);
                $this->appendHistory($historyPath, $this->historyRow($variant, 'promoted_no_prior_baseline', $plan, $oldMetrics, $newMetrics, $force, 'storage/app/prediction/'.$spec['artifact']));
                $this->info(sprintf('%s: promoted (no prior retrain_evaluation baseline to compare against, new macro F1 %.4f).', $variant, $newMetrics['macro_f1'] ?? 0.0));
                continue;
            }

            if ($oldMetrics['purge_days'] !== $newMetrics['purge_days']) {
                // The evaluation methodology itself changed (Fase S added a purge gap equal to the
                // label horizon), so the two macro_f1 values measure different things. Gating one
                // against the other would misread a measurement correction as a model regression
                // and reject a model that is not actually worse. Promote and re-baseline instead --
                // the next retrain compares like against like.
                $this->promote($predictionDir, $candidateDir, $spec, $variant, $timestamp);
                $this->appendHistory($historyPath, $this->historyRow($variant, 'promoted_eval_methodology_changed', $plan, $oldMetrics, $newMetrics, $force, 'storage/app/prediction/'.$spec['artifact']));
                $this->warn(sprintf(
                    '%s: promoted WITHOUT degradation gating -- walk-forward purge_days changed %d -> %d, so old macro F1 %.4f and new %.4f are not comparable. Next retrain re-gates normally.',
                    $variant,
                    $oldMetrics['purge_days'],
                    $newMetrics['purge_days'],
                    $oldMetrics['macro_f1'] ?? 0.0,
                    $newMetrics['macro_f1'] ?? 0.0
                ));
                Log::warning('Production model promoted across an evaluation methodology change', [
                    'variant' => $variant,
                    'old_purge_days' => $oldMetrics['purge_days'],
                    'new_purge_days' => $newMetrics['purge_days'],
                    'old_macro_f1' => $oldMetrics['macro_f1'],
                    'new_macro_f1' => $newMetrics['macro_f1'],
                ]);
                continue;
            }

            $macroDelta = ($newMetrics['macro_f1'] ?? 0.0) - ($oldMetrics['macro_f1'] ?? 0.0);
            if ($macroDelta < -self::DEGRADATION_THRESHOLD) {
                $candidateArtifact = $predictionDir.'/'.pathinfo($spec['artifact'], PATHINFO_FILENAME).'_candidate.joblib';
                $candidateMetadata = $predictionDir.'/'.pathinfo($spec['metadata'], PATHINFO_FILENAME).'_candidate.json';
                File::copy($newArtifactPath, $candidateArtifact);
                File::copy($newMetadataPath, $candidateMetadata);
                $this->appendHistory($historyPath, $this->historyRow($variant, 'candidate_only', $plan, $oldMetrics, $newMetrics, $force, $candidateArtifact));
                $this->warn(sprintf('%s: new model is worse, saved as candidate only (macro F1 old %.4f -> new %.4f).', $variant, $oldMetrics['macro_f1'] ?? 0.0, $newMetrics['macro_f1'] ?? 0.0));
                Log::warning('Production model candidate rejected due to macro F1 degradation', [
                    'variant' => $variant,
                    'old_macro_f1' => $oldMetrics['macro_f1'],
                    'new_macro_f1' => $newMetrics['macro_f1'],
                    'candidate_artifact' => $candidateArtifact,
                ]);
                continue;
            }

            $this->promote($predictionDir, $candidateDir, $spec, $variant, $timestamp);
            $this->appendHistory($historyPath, $this->historyRow($variant, 'promoted', $plan, $oldMetrics, $newMetrics, $force, 'storage/app/prediction/'.$spec['artifact']));
            $this->info(sprintf('%s: promoted (macro F1 old %.4f -> new %.4f).', $variant, $oldMetrics['macro_f1'] ?? 0.0, $newMetrics['macro_f1'] ?? 0.0));
        }

        return $exitCode;
    }

    protected function promote(string $predictionDir, string $candidateDir, array $spec, string $variant, Carbon $timestamp): void
    {
        $archiveDir = $predictionDir.'/archive';
        File::ensureDirectoryExists($archiveDir);
        $suffix = $timestamp->format('Ymd_His');
        foreach (['artifact', 'metadata'] as $kind) {
            $productionPath = $predictionDir.'/'.$spec[$kind];
            if (File::exists($productionPath)) {
                File::copy($productionPath, $archiveDir.'/'.pathinfo($spec[$kind], PATHINFO_FILENAME).'_'.$suffix.'.'.pathinfo($spec[$kind], PATHINFO_EXTENSION));
            }
            File::copy($candidateDir.'/'.$spec[$kind], $productionPath);
        }
    }

    protected function selectedVariant(): string|false|null
    {
        $variant = trim((string) ($this->option('variant') ?? ''));
        if ($variant === '') {
            return null;
        }
        if (! array_key_exists($variant, self::VARIANTS)) {
            $this->error('Invalid --variant value. Use one of: '.implode(', ', array_keys(self::VARIANTS)));

            return false;
        }

        return $variant;
    }

    protected function runTrainingProcess(string $variant, string $candidateDir): Process
    {
        $script = base_path(env('PREDICTION_PRODUCTION_TRAIN_SCRIPT', 'quant/train_production_models.py'));
        $python = env('PYTHON_BINARY', 'python3');
        $process = new Process([$python, $script, '--variant', $variant, '--output-dir', $candidateDir], base_path(), null, null, 900);
        $process->run(function (string $type, string $buffer): void {
            $this->output->write($buffer);
        });

        return $process;
    }

    protected function buildPlans(string $predictionDir, array $variants): array
    {
        $stockIds = Stock::whereIn('code', self::OFFICIAL_TICKERS)->pluck('id');

        $plans = [];
        foreach ($variants as $variant => $spec) {
            $metadata = $this->readJson($predictionDir.'/'.$spec['metadata']);
            $trainedAt = $this->parseDate($metadata['trained_at'] ?? null);

            $newPriceRows = $trainedAt
                ? StockPrice::whereIn('stock_id', $stockIds)->where('interval_type', '1d')->where('price_date', '>', $trainedAt)->count()
                : StockPrice::whereIn('stock_id', $stockIds)->where('interval_type', '1d')->count();
            $newArticleRows = $trainedAt
                ? NewsArticle::whereIn('stock_id', $stockIds)->whereNotNull('published_at')->where('published_at', '>', $trainedAt)->count()
                : NewsArticle::whereIn('stock_id', $stockIds)->whereNotNull('published_at')->count();

            $plans[$variant] = [
                'trained_at' => $trainedAt?->toIso8601String(),
                'new_price_rows' => $newPriceRows,
                'new_article_rows' => $newArticleRows,
                'rows_new_data' => $newPriceRows + $newArticleRows,
                'has_new_data' => $trainedAt === null || $newPriceRows > 0 || $newArticleRows > 0,
            ];
        }

        return $plans;
    }

    protected function retrainEvalFromMetadata(array $metadata): array
    {
        $eval = is_array($metadata['retrain_evaluation'] ?? null) ? $metadata['retrain_evaluation'] : [];

        return [
            'macro_f1' => isset($eval['macro_f1']) ? (float) $eval['macro_f1'] : null,
            'directional_accuracy' => isset($eval['directional_accuracy']) ? (float) $eval['directional_accuracy'] : null,
            'fold_count' => $eval['fold_count'] ?? null,
            // Metadata written before Fase S has no purge_days key at all; treat that as 0 (the
            // old no-gap behaviour) so it can be compared against the new value explicitly.
            'purge_days' => isset($eval['purge_days']) ? (int) $eval['purge_days'] : 0,
        ];
    }

    protected function historyRow(string $variant, string $decision, array $plan, ?array $oldMetrics, ?array $newMetrics, bool $force, ?string $artifactPath = null): array
    {
        return [
            'timestamp' => now('UTC')->toIso8601String(),
            'model' => $variant,
            'trigger' => $force ? 'forced' : 'manual',
            'rows_new_data' => $plan['rows_new_data'],
            'old_macro_f1' => $oldMetrics['macro_f1'] ?? null,
            'new_macro_f1' => $newMetrics['macro_f1'] ?? null,
            'decision' => $decision,
            'artifact_path' => $artifactPath,
            'trained_at_before' => $plan['trained_at'],
            'old_metrics' => $oldMetrics,
            'new_metrics' => $newMetrics,
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
