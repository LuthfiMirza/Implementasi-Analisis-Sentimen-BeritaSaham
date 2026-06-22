<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class RetrainVolatilePredictionModelsCommandTest extends TestCase
{
    private string $modelDir;
    private string $scriptPath;

    protected function setUp(): void
    {
        parent::setUp();

        $this->modelDir = storage_path('framework/testing/prediction-retrain-'.uniqid());
        $this->scriptPath = storage_path('framework/testing/fake_train_volatile_'.uniqid().'.php');
        File::ensureDirectoryExists($this->modelDir);
        putenv('PREDICTION_RETRAIN_MODEL_DIR='.$this->modelDir);
        putenv('PREDICTION_VOLATILE_TRAIN_SCRIPT='.$this->relativeToBasePath($this->scriptPath));
        putenv('PYTHON_BINARY=php');

        $this->seedVolatileStocks();
        $this->writeProductionArtifacts(0.40);
    }

    protected function tearDown(): void
    {
        putenv('PREDICTION_RETRAIN_MODEL_DIR');
        putenv('PREDICTION_VOLATILE_TRAIN_SCRIPT');
        putenv('PYTHON_BINARY');
        if (isset($this->modelDir)) {
            File::deleteDirectory($this->modelDir);
        }
        if (isset($this->scriptPath) && File::exists($this->scriptPath)) {
            File::delete($this->scriptPath);
        }

        parent::tearDown();
    }

    public function test_dry_run_does_not_retrain_but_logs_plan(): void
    {
        $this->writeFakeTrainScript(0.45);

        $this->artisan('prediction:retrain-volatile', ['--dry-run' => true, '--force' => true])
            ->expectsOutputToContain('would_retrain')
            ->assertExitCode(0);

        $this->assertFileDoesNotExist($this->modelDir.'/candidates');
        $this->assertSame([], $this->historyRows());
    }

    public function test_skips_when_no_new_data_exists(): void
    {
        $this->writeFakeTrainScript(0.45);

        $this->artisan('prediction:retrain-volatile')
            ->expectsOutputToContain('skip_no_new_data')
            ->assertExitCode(0);

        $history = $this->historyRows();
        $this->assertCount(3, $history);
        $this->assertSame(['skipped', 'skipped', 'skipped'], array_column($history, 'decision'));
        $this->assertSame(['manual', 'manual', 'manual'], array_column($history, 'trigger'));
    }

    public function test_model_option_limits_retrain_to_one_model(): void
    {
        $this->writeFakeTrainScript(0.42);

        $this->artisan('prediction:retrain-volatile', ['--force' => true, '--model' => 'dewa_technical'])
            ->expectsOutputToContain('dewa_technical')
            ->assertExitCode(0);

        $history = $this->historyRows();
        $this->assertCount(1, $history);
        $this->assertSame('dewa_technical', $history[0]['model']);
        $this->assertSame('promoted', $history[0]['decision']);
        $this->assertSame('production-bumi_technical', File::get($this->modelDir.'/model_bumi_technical.joblib'));
    }

    public function test_worse_candidate_does_not_replace_production_model(): void
    {
        $this->writeFakeTrainScript(0.30);
        $before = File::get($this->modelDir.'/model_bumi_technical.joblib');

        $this->artisan('prediction:retrain-volatile', ['--force' => true])
            ->expectsOutputToContain('candidate only')
            ->assertExitCode(0);

        $this->assertSame($before, File::get($this->modelDir.'/model_bumi_technical.joblib'));
        $this->assertDirectoryExists($this->modelDir.'/candidates');
        $this->assertFileExists($this->modelDir.'/model_bumi_technical_candidate.joblib');
        $this->assertContains('candidate_only', array_column($this->historyRows(), 'decision'));
    }

    public function test_acceptable_candidate_is_archived_and_replaces_production(): void
    {
        $this->writeFakeTrainScript(0.42);

        $this->artisan('prediction:retrain-volatile', ['--force' => true])
            ->expectsOutputToContain('promoted')
            ->assertExitCode(0);

        $this->assertSame('candidate-bumi_technical', File::get($this->modelDir.'/model_bumi_technical.joblib'));
        $this->assertNotEmpty(File::files($this->modelDir.'/archive'));
        $this->assertContains('promoted', array_column($this->historyRows(), 'decision'));
    }

    private function seedVolatileStocks(): void
    {
        foreach (['BUMI', 'DEWA'] as $code) {
            $stock = Stock::factory()->create(['code' => $code, 'is_active' => true]);
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
    }

    private function writeProductionArtifacts(float $macroF1): void
    {
        foreach ($this->specs() as $variant => $spec) {
            File::put($this->modelDir.'/'.$spec['artifact'], 'production-'.$variant);
            File::put($this->modelDir.'/'.$spec['metadata'], json_encode([
                'model_variant' => $variant,
                'trained_at' => '2026-06-21T22:43:26+07:00',
                'research_summary' => [
                    'macro_f1' => $macroF1,
                    'directional_accuracy' => 0.50,
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
        'research_summary' => [
            'macro_f1' => $macroF1,
            'directional_accuracy' => 0.55,
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
            'bumi_technical' => ['artifact' => 'model_bumi_technical.joblib', 'metadata' => 'model_bumi_technical_metadata.json'],
            'dewa_regime' => ['artifact' => 'model_dewa_regime.joblib', 'metadata' => 'model_dewa_regime_metadata.json'],
            'dewa_technical' => ['artifact' => 'model_dewa_technical.joblib', 'metadata' => 'model_dewa_technical_metadata.json'],
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
