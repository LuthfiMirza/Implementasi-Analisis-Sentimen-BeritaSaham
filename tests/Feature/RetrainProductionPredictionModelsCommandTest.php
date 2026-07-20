<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class RetrainProductionPredictionModelsCommandTest extends TestCase
{
    private string $modelDir;
    private string $datasetRelDir;
    private string $scriptPath;

    protected function setUp(): void
    {
        parent::setUp();

        $this->modelDir = storage_path('framework/testing/prediction-retrain-production-'.uniqid());
        $this->datasetRelDir = 'storage/framework/testing/prediction-retrain-production-dataset-'.uniqid();
        $this->scriptPath = storage_path('framework/testing/fake_train_production_'.uniqid().'.php');
        File::ensureDirectoryExists($this->modelDir);
        File::ensureDirectoryExists(base_path($this->datasetRelDir));

        putenv('PREDICTION_RETRAIN_MODEL_DIR='.$this->modelDir);
        putenv('PREDICTION_RETRAIN_DATASET_DIR='.$this->datasetRelDir);
        putenv('PREDICTION_PRODUCTION_TRAIN_SCRIPT='.$this->relativeToBasePath($this->scriptPath));
        putenv('PYTHON_BINARY=php');

        // BBCA has a real historical CSV under data/stocks/BBCA.csv (used by every V6A/V6B
        // research script this whole session) -- creating the Stock row is enough for
        // prediction:export-research-dataset to run for real against genuine history, without
        // needing to fabricate thousands of synthetic OHLCV rows just to satisfy feature checks.
        $this->seedOfficialStock();
        $this->writeProductionArtifacts(0.35);
    }

    protected function tearDown(): void
    {
        putenv('PREDICTION_RETRAIN_MODEL_DIR');
        putenv('PREDICTION_RETRAIN_DATASET_DIR');
        putenv('PREDICTION_PRODUCTION_TRAIN_SCRIPT');
        putenv('PYTHON_BINARY');
        if (isset($this->modelDir)) {
            File::deleteDirectory($this->modelDir);
        }
        if (isset($this->datasetRelDir)) {
            File::deleteDirectory(base_path($this->datasetRelDir));
        }
        if (isset($this->scriptPath) && File::exists($this->scriptPath)) {
            File::delete($this->scriptPath);
        }

        parent::tearDown();
    }

    public function test_dry_run_does_not_retrain_but_logs_plan(): void
    {
        $this->writeFakeTrainScript(0.45);

        $this->artisan('prediction:retrain-production', ['--dry-run' => true, '--force' => true])
            ->expectsOutputToContain('would_retrain')
            ->assertExitCode(0);

        $this->assertFileDoesNotExist($this->modelDir.'/candidates');
        $this->assertFileDoesNotExist(base_path($this->datasetRelDir.'/dataset_v6a.csv'));
        $this->assertSame([], $this->historyRows());
    }

    public function test_skips_when_no_new_data_exists(): void
    {
        $this->writeFakeTrainScript(0.45);

        $this->artisan('prediction:retrain-production')
            ->expectsOutputToContain('skip_no_new_data')
            ->assertExitCode(0);

        $history = $this->historyRows();
        $this->assertCount(2, $history);
        $this->assertSame(['skipped', 'skipped'], array_column($history, 'decision'));
        $this->assertSame(['manual', 'manual'], array_column($history, 'trigger'));
    }

    public function test_variant_option_limits_retrain_to_one_variant(): void
    {
        $this->writeFakeTrainScript(0.42);

        $this->artisan('prediction:retrain-production', ['--force' => true, '--variant' => 'technical_sentiment'])
            ->expectsOutputToContain('technical_sentiment')
            ->assertExitCode(0);

        $history = $this->historyRows();
        $this->assertCount(1, $history);
        $this->assertSame('technical_sentiment', $history[0]['model']);
        $this->assertSame('promoted', $history[0]['decision']);
        $this->assertSame('production-technical', File::get($this->modelDir.'/model_technical_v6a.joblib'));
        $this->assertSame('candidate-technical_sentiment', File::get($this->modelDir.'/model_technical_sentiment_v6b.joblib'));
        $this->assertFileExists(base_path($this->datasetRelDir.'/dataset_v6a.csv'));
        $this->assertFileExists(base_path($this->datasetRelDir.'/dataset_v6b_10ticker.csv'));
    }

    public function test_worse_candidate_does_not_replace_production_model(): void
    {
        $this->writeFakeTrainScript(0.20);
        $before = File::get($this->modelDir.'/model_technical_v6a.joblib');

        $this->artisan('prediction:retrain-production', ['--force' => true])
            ->expectsOutputToContain('candidate only')
            ->assertExitCode(0);

        $this->assertSame($before, File::get($this->modelDir.'/model_technical_v6a.joblib'));
        $this->assertDirectoryExists($this->modelDir.'/candidates');
        $this->assertFileExists($this->modelDir.'/model_technical_v6a_candidate.joblib');
        $this->assertContains('candidate_only', array_column($this->historyRows(), 'decision'));
    }

    public function test_acceptable_candidate_is_archived_and_replaces_production(): void
    {
        $this->writeFakeTrainScript(0.42);

        $this->artisan('prediction:retrain-production', ['--force' => true])
            ->expectsOutputToContain('promoted')
            ->assertExitCode(0);

        $this->assertSame('candidate-technical', File::get($this->modelDir.'/model_technical_v6a.joblib'));
        $this->assertSame('candidate-technical_sentiment', File::get($this->modelDir.'/model_technical_sentiment_v6b.joblib'));
        $this->assertNotEmpty(File::files($this->modelDir.'/archive'));
        $this->assertContains('promoted', array_column($this->historyRows(), 'decision'));
    }

    public function test_promotes_unconditionally_when_no_prior_baseline_exists(): void
    {
        File::delete($this->modelDir.'/model_technical_v6a_metadata.json');
        File::delete($this->modelDir.'/model_technical_sentiment_v6b_metadata.json');
        $this->writeFakeTrainScript(0.10);

        $this->artisan('prediction:retrain-production', ['--force' => true])
            ->assertExitCode(0);

        $history = $this->historyRows();
        $this->assertSame(['promoted_no_prior_baseline', 'promoted_no_prior_baseline'], array_column($history, 'decision'));
    }

    private function seedOfficialStock(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'is_active' => true]);
        StockPrice::factory()->create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::parse('2026-06-16'),
            'interval_type' => '1d',
        ]);
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'published_at' => Carbon::parse('2026-06-16'),
        ]);
    }

    private function writeProductionArtifacts(float $macroF1): void
    {
        foreach ($this->specs() as $variant => $spec) {
            File::put($this->modelDir.'/'.$spec['artifact'], 'production-'.$variant);
            File::put($this->modelDir.'/'.$spec['metadata'], json_encode([
                'model_variant' => $variant,
                'trained_at' => '2026-06-21T22:43:26+07:00',
                'retrain_evaluation' => [
                    'macro_f1' => $macroF1,
                    'directional_accuracy' => 0.40,
                    'fold_count' => 8,
                ],
            ], JSON_PRETTY_PRINT));
        }
    }

    private function writeFakeTrainScript(float $macroF1): void
    {
        $specs = var_export($this->specs(), true);
        File::put($this->scriptPath, <<<'PHP_SCRIPT'
<?php
$outputDir = $argv[array_search('--output-dir', $argv, true) + 1] ?? null;
$variantArg = $argv[array_search('--variant', $argv, true) + 1] ?? 'all';
if (! $outputDir) { exit(2); }
@mkdir($outputDir, 0777, true);
$macroF1 = __MACRO_F1__;
$specs = __SPECS__;
foreach ($specs as $variant => $spec) {
    if ($variantArg !== 'all' && $variantArg !== $variant) { continue; }
    file_put_contents($outputDir.'/'.$spec['artifact'], 'candidate-'.$variant);
    file_put_contents($outputDir.'/'.$spec['metadata'], json_encode([
        'model_variant' => $variant,
        'trained_at' => date('c'),
        'retrain_evaluation' => [
            'macro_f1' => $macroF1,
            'directional_accuracy' => 0.42,
            'fold_count' => 8,
        ],
    ], JSON_PRETTY_PRINT));
}
echo "fake train complete\n";
PHP_SCRIPT);
        File::put($this->scriptPath, str_replace(['__MACRO_F1__', '__SPECS__'], [(string) $macroF1, $specs], File::get($this->scriptPath)));
    }

    private function specs(): array
    {
        return [
            'technical' => ['artifact' => 'model_technical_v6a.joblib', 'metadata' => 'model_technical_v6a_metadata.json'],
            'technical_sentiment' => ['artifact' => 'model_technical_sentiment_v6b.joblib', 'metadata' => 'model_technical_sentiment_v6b_metadata.json'],
        ];
    }

    private function historyRows(): array
    {
        $path = $this->modelDir.'/retrain_history.jsonl';
        if (! File::exists($path)) {
            return [];
        }

        return collect(explode("\n", trim(File::get($path))))
            ->filter()
            ->map(fn (string $line): array => json_decode($line, true))
            ->values()
            ->all();
    }

    private function relativeToBasePath(string $path): string
    {
        return str_starts_with($path, base_path().DIRECTORY_SEPARATOR)
            ? substr($path, strlen(base_path()) + 1)
            : $path;
    }
}
