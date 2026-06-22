<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Log;
use Symfony\Component\Process\Process;

class RetrainVolatilePredictionModelsCommand extends Command
{
    protected $signature = 'prediction:retrain-volatile
        {--dry-run : Show planned retrain without executing}
        {--force : Retrain even when no new data exists}
        {--model= : Optional model variant: bumi_technical, dewa_regime, dewa_technical}';

    protected $description = 'Safely retrain BUMI/DEWA volatile-stock prediction artifacts with backup, candidate gating, and JSONL history.';

    protected const DEGRADATION_THRESHOLD = 0.05;

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
        $selectedModel = $this->selectedModel();
        if ($selectedModel === false) {
            return self::FAILURE;
        }

        $predictionDir = env('PREDICTION_RETRAIN_MODEL_DIR', storage_path('app/prediction'));
        $historyPath = $predictionDir.'/retrain_history.jsonl';
        $timestamp = now('Asia/Jakarta');
        $force = (bool) $this->option('force');
        $dryRun = (bool) $this->option('dry-run');
        $variants = $selectedModel ? [$selectedModel => self::VARIANTS[$selectedModel]] : self::VARIANTS;
        $plans = $this->buildPlans($predictionDir, $timestamp, $variants);

        foreach ($plans as $variant => $plan) {
            $willRetrain = $force || $plan['has_new_data'];
            $this->line(sprintf(
                '%s: latest_data=%s trained_at=%s rows_new_data=%d estimated_training_time=%s decision=%s',
                $variant,
                $plan['latest_data_at'] ?? 'n/a',
                $plan['trained_at'] ?? 'n/a',
                $plan['rows_new_data'],
                $this->estimatedTrainingTime($variant),
                $willRetrain ? ($dryRun ? 'would_retrain' : 'retrain') : 'skip_no_new_data'
            ));
        }

        if ($dryRun) {
            $this->info('Dry run complete; no Python process was called and no artifact was changed.');

            return self::SUCCESS;
        }

        $exitCode = self::SUCCESS;
        foreach ($variants as $variant => $spec) {
            $plan = $plans[$variant];
            if (! $force && ! $plan['has_new_data']) {
                $this->appendHistory($historyPath, $this->historyRow($variant, 'skipped', $plan, null, null, $force));
                $this->info(sprintf('%s: no new data since %s, skip.', $variant, $plan['trained_at'] ?? 'unknown'));
                continue;
            }

            $candidateDir = $predictionDir.'/candidates/retrain_'.$timestamp->format('Ymd_His').'_'.$variant;
            File::ensureDirectoryExists($candidateDir);

            $process = $this->runTrainingProcess($variant, $candidateDir);
            if (! $process->isSuccessful()) {
                $this->error($variant.': retrain script failed. Candidate directory preserved: '.$candidateDir);
                Log::warning('Volatile model retrain failed', [
                    'model' => $variant,
                    'output' => trim($process->getErrorOutput() ?: $process->getOutput()),
                ]);
                $exitCode = self::FAILURE;
                continue;
            }

            $oldMetadataPath = $predictionDir.'/'.$spec['metadata'];
            $newMetadataPath = $candidateDir.'/'.$spec['metadata'];
            $newArtifactPath = $candidateDir.'/'.$spec['artifact'];
            $oldMetrics = $this->metricsFromMetadata($this->readJson($oldMetadataPath));
            $newMetrics = $this->metricsFromMetadata($this->readJson($newMetadataPath));

            if (! File::exists($newMetadataPath) || ! File::exists($newArtifactPath)) {
                $this->warn($variant.': candidate artifact missing; production unchanged.');
                Log::warning('Volatile model candidate artifact missing', ['model' => $variant, 'candidate_dir' => $candidateDir]);
                $exitCode = self::FAILURE;
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
                Log::warning('Volatile model candidate rejected due to macro F1 degradation', [
                    'model' => $variant,
                    'old_macro_f1' => $oldMetrics['macro_f1'] ?? null,
                    'new_macro_f1' => $newMetrics['macro_f1'] ?? null,
                    'candidate_artifact' => $candidateArtifact,
                ]);
                continue;
            }

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

            $artifactPath = 'storage/app/prediction/'.$spec['artifact'];
            $this->appendHistory($historyPath, $this->historyRow($variant, 'promoted', $plan, $oldMetrics, $newMetrics, $force, $artifactPath));
            $this->info(sprintf('%s: promoted (macro F1 old %.4f -> new %.4f).', $variant, $oldMetrics['macro_f1'] ?? 0.0, $newMetrics['macro_f1'] ?? 0.0));
        }

        return $exitCode;
    }

    protected function selectedModel(): string|false|null
    {
        $model = trim((string) ($this->option('model') ?? ''));
        if ($model === '') {
            return null;
        }
        if (! array_key_exists($model, self::VARIANTS)) {
            $this->error('Invalid --model value. Use one of: '.implode(', ', array_keys(self::VARIANTS)));

            return false;
        }

        return $model;
    }

    protected function runTrainingProcess(string $variant, string $candidateDir): Process
    {
        $script = base_path(env('PREDICTION_VOLATILE_TRAIN_SCRIPT', 'quant/train_volatile_stock_models.py'));
        $python = env('PYTHON_BINARY', 'python3');
        $process = new Process([$python, $script, '--variant', $variant, '--output-dir', $candidateDir], base_path(), null, null, 600);
        $process->run(function (string $type, string $buffer): void {
            $this->output->write($buffer);
        });

        return $process;
    }

    protected function buildPlans(string $predictionDir, Carbon $now, array $variants): array
    {
        $plans = [];
        foreach ($variants as $variant => $spec) {
            $metadata = $this->readJson($predictionDir.'/'.$spec['metadata']);
            $trainedAt = $this->parseDate($metadata['trained_at'] ?? null);
            $ticker = $spec['ticker'];
            $stock = Stock::where('code', $ticker)->first();
            $canonicalPrices = $stock
                ? StockPrice::canonicalize(StockPrice::where('stock_id', $stock->id)->where('interval_type', '1d')->get())
                : collect();
            $latestPriceAt = $canonicalPrices->last()?->price_date;
            $latestArticleAt = $stock
                ? NewsArticle::where('stock_id', $stock->id)->whereNotNull('published_at')->max('published_at')
                : null;
            $latestDataAt = collect([$this->parseDate($latestPriceAt), $this->parseDate($latestArticleAt)])->filter()->max();
            $newPriceRows = $trainedAt
                ? $canonicalPrices->filter(fn (StockPrice $row): bool => $this->parseDate($row->price_date)?->gt($trainedAt) ?? false)->count()
                : $canonicalPrices->count();
            $newArticleRows = $stock && $trainedAt
                ? NewsArticle::where('stock_id', $stock->id)->whereNotNull('published_at')->where('published_at', '>', $trainedAt)->count()
                : 0;

            $plans[$variant] = [
                'ticker' => $ticker,
                'trained_at' => $trainedAt?->toIso8601String(),
                'latest_data_at' => $latestDataAt instanceof Carbon ? $latestDataAt->toIso8601String() : null,
                'new_price_rows' => $newPriceRows,
                'new_article_rows' => $newArticleRows,
                'rows_new_data' => $newPriceRows + $newArticleRows,
                'has_new_data' => $trainedAt === null || $newPriceRows > 0 || $newArticleRows > 0,
                'checked_at' => $now->toIso8601String(),
            ];
        }

        return $plans;
    }

    protected function estimatedTrainingTime(string $variant): string
    {
        return match ($variant) {
            'bumi_technical' => '~2-5s',
            'dewa_regime', 'dewa_technical' => '~1-3s',
            default => '~1-5s',
        };
    }

    protected function metricsFromMetadata(array $metadata): array
    {
        $summary = is_array($metadata['research_summary'] ?? null) ? $metadata['research_summary'] : [];
        return [
            'macro_f1' => isset($summary['macro_f1']) ? (float) $summary['macro_f1'] : null,
            'directional_accuracy' => isset($summary['directional_accuracy']) ? (float) $summary['directional_accuracy'] : null,
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
            'ticker' => $plan['ticker'],
            'trained_at_before' => $plan['trained_at'],
            'latest_data_at' => $plan['latest_data_at'],
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
