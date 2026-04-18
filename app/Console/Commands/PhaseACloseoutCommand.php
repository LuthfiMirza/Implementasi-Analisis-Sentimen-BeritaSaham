<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\Analytics\MacroRegulatorySignalService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Symfony\Component\Process\Process;

#[Signature('phase-a:closeout {--output-dir=output} {--skip-tests : Skip running the core Python/PHP test suites} {--skip-freeze-baseline : Do not refresh the Python baseline before evaluating closeout}')]
#[Description('Run the final operational close-out checks for Phase A and emit report artifacts')]
class PhaseACloseoutCommand extends Command
{
    public function handle(MacroRegulatorySignalService $macroRegulatorySignalService): int
    {
        $outputDir = base_path((string) $this->option('output-dir'));
        if (! is_dir($outputDir)) {
            mkdir($outputDir, 0777, true);
        }

        $baselineRefresh = $this->refreshBaselineIfNeeded($outputDir);
        $baselineStatus = $this->loadBaselineStatus($outputDir);
        if (! empty($baselineRefresh['warnings'])) {
            $baselineStatus['warnings'] = array_merge($baselineStatus['warnings'], $baselineRefresh['warnings']);
        }

        $ojkStatus = $this->inspectOjkBackfill();
        $macroStatus = $this->inspectMacroSignal($macroRegulatorySignalService);
        $testsStatus = $this->option('skip-tests')
            ? $this->skippedTestsStatus()
            : $this->runCoreTests();

        $closeout = $this->determineCloseoutStatus(
            $baselineStatus,
            $ojkStatus,
            $macroStatus,
            $testsStatus
        );
        $reportText = $this->buildReport(
            $baselineStatus,
            $ojkStatus,
            $macroStatus,
            $testsStatus,
            $closeout
        );

        $reportPath = $outputDir.'/phase_a_closeout_report.txt';
        file_put_contents($reportPath, $reportText);

        $statusPayload = [
            'generated_at' => now()->toIso8601String(),
            'status' => $closeout['status'],
            'reason' => $closeout['reason'],
            'blocking_items' => $closeout['blocking_items'],
            'notes' => $closeout['notes'],
            'baseline' => $baselineStatus,
            'ojk_backfill' => $ojkStatus,
            'macro_regulatory_signal' => $macroStatus,
            'tests' => $testsStatus,
        ];

        $statusPath = $outputDir.'/phase_a_closeout_status.json';
        file_put_contents(
            $statusPath,
            json_encode($statusPayload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );

        $this->info('Phase A closeout complete.');
        $this->line('Status: '.$closeout['status']);
        $this->line('Reason: '.$closeout['reason']);
        $this->line('Report: '.$reportPath);
        $this->line('JSON: '.$statusPath);

        return self::SUCCESS;
    }

    protected function refreshBaselineIfNeeded(string $outputDir): array
    {
        if ($this->option('skip-freeze-baseline')) {
            return ['status' => 'skipped', 'warnings' => []];
        }

        $relativeOutputDir = ltrim(str_replace(base_path(), '', $outputDir), DIRECTORY_SEPARATOR);
        $relativeOutputDir = $relativeOutputDir !== '' ? $relativeOutputDir : 'output';
        $command = [
            'python3',
            '-m',
            'quant.freeze_phase_a_baseline',
            '--output-dir',
            $relativeOutputDir,
        ];
        $process = new Process($command, base_path());
        $process->setTimeout(180);
        $process->run();

        if ($process->isSuccessful()) {
            return ['status' => 'passed', 'warnings' => []];
        }

        return [
            'status' => 'failed',
            'warnings' => [
                'Baseline freeze command failed before closeout: '.trim($process->getErrorOutput() ?: $process->getOutput()),
            ],
        ];
    }

    protected function loadBaselineStatus(string $outputDir): array
    {
        $paths = [
            $outputDir.'/phase_a_baseline_final.json',
            base_path('config/phase_a_baseline.json'),
        ];

        foreach ($paths as $path) {
            if (! is_file($path)) {
                continue;
            }

            try {
                $payload = json_decode((string) file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
            } catch (\Throwable $e) {
                return [
                    'available' => false,
                    'source_path' => $path,
                    'baseline_status' => 'draft',
                    'readiness_status' => 'partially_ready',
                    'default_volume_spike_threshold' => 2.0,
                    'strict_mode_default' => false,
                    'adaptive_threshold_enabled' => false,
                    'group_override_count' => 0,
                    'strict_mode_decision_code' => null,
                    'warnings' => ['Failed to parse baseline config: '.$e->getMessage()],
                ];
            }

            return [
                'available' => true,
                'source_path' => $path,
                'baseline_status' => (string) ($payload['baseline_status'] ?? 'draft'),
                'readiness_status' => (string) ($payload['readiness_status'] ?? 'partially_ready'),
                'default_volume_spike_threshold' => (float) ($payload['default_volume_spike_threshold'] ?? 2.0),
                'strict_mode_default' => (bool) ($payload['strict_mode_default'] ?? false),
                'adaptive_threshold_enabled' => (bool) ($payload['adaptive_threshold_enabled'] ?? false),
                'group_override_count' => count($payload['group_threshold_overrides'] ?? []),
                'strict_mode_decision_code' => $payload['strict_mode_decision_code'] ?? null,
                'warnings' => array_values($payload['warnings'] ?? []),
            ];
        }

        return [
            'available' => false,
            'source_path' => null,
            'baseline_status' => 'draft',
            'readiness_status' => 'partially_ready',
            'default_volume_spike_threshold' => 2.0,
            'strict_mode_default' => false,
            'adaptive_threshold_enabled' => false,
            'group_override_count' => 0,
            'strict_mode_decision_code' => null,
            'warnings' => ['Baseline config not found.'],
        ];
    }

    protected function inspectOjkBackfill(): array
    {
        $minCount = (int) config('analytics.phase_a_closeout.min_ojk_article_count', 5);
        $minHistoryDays = (int) config('analytics.phase_a_closeout.min_historical_days', 30);

        try {
            $query = NewsArticle::query()
                ->whereNull('stock_id')
                ->where('source_provider', 'ojk_rss')
                ->whereNotNull('published_at');

            $count = (int) $query->count();
            $oldest = $query->min('published_at');
            $newest = $query->max('published_at');
            $neutralCount = (int) NewsArticle::query()
                ->whereNull('stock_id')
                ->where('source_provider', 'ojk_rss')
                ->where('sentiment_label', 'neutral')
                ->count();

            $oldestDate = $oldest ? Carbon::parse($oldest) : null;
            $newestDate = $newest ? Carbon::parse($newest) : null;
            $hasHistoryCoverage = $oldestDate !== null && $oldestDate->lessThanOrEqualTo(now()->subDays($minHistoryDays));
            $ready = $count >= $minCount && $hasHistoryCoverage;

            return [
                'available' => true,
                'ready' => $ready,
                'article_count' => $count,
                'neutral_article_count' => $neutralCount,
                'neutral_only' => $count > 0 && $neutralCount === $count,
                'oldest_published_at' => $oldestDate?->toDateString(),
                'newest_published_at' => $newestDate?->toDateString(),
                'min_article_count_required' => $minCount,
                'min_history_days_required' => $minHistoryDays,
                'error' => null,
            ];
        } catch (\Throwable $e) {
            return [
                'available' => false,
                'ready' => false,
                'article_count' => 0,
                'neutral_article_count' => 0,
                'neutral_only' => false,
                'oldest_published_at' => null,
                'newest_published_at' => null,
                'min_article_count_required' => $minCount,
                'min_history_days_required' => $minHistoryDays,
                'error' => $e->getMessage(),
            ];
        }
    }

    protected function inspectMacroSignal(MacroRegulatorySignalService $service): array
    {
        $featureFlagEnabled = (bool) config('analytics.macro_regulatory_signal.enabled', true);

        try {
            $articles = NewsArticle::query()
                ->whereNull('stock_id')
                ->where('source_provider', 'ojk_rss')
                ->whereNotNull('published_at')
                ->where('published_at', '>=', now()->subDays(30))
                ->orderBy('published_at')
                ->get();

            $signal = $service->evaluate($articles, 30, now(), $featureFlagEnabled);

            return [
                'feature_flag_enabled' => $featureFlagEnabled,
                'ready' => $featureFlagEnabled && is_array($signal) && array_key_exists('confidence_multiplier', $signal),
                'signal' => $signal,
                'neutral_only_handled' => $featureFlagEnabled
                    && ($signal['active'] ?? false)
                    && array_key_exists('confidence_multiplier', $signal),
                'error' => null,
            ];
        } catch (\Throwable $e) {
            return [
                'feature_flag_enabled' => $featureFlagEnabled,
                'ready' => false,
                'signal' => [
                    'attention_regime' => 'unavailable',
                    'confidence_multiplier' => 'n/a',
                    'narrative' => 'Macro regulatory signal tidak bisa dievaluasi karena akses database gagal.',
                ],
                'neutral_only_handled' => false,
                'error' => $e->getMessage(),
            ];
        }
    }

    protected function skippedTestsStatus(): array
    {
        return [
            'python' => ['status' => 'skipped', 'command' => null, 'summary' => 'Skipped by --skip-tests'],
            'php' => ['status' => 'skipped', 'command' => null, 'summary' => 'Skipped by --skip-tests'],
        ];
    }

    protected function runCoreTests(): array
    {
        $pythonCommand = [
            'python3',
            '-m',
            'unittest',
            'quant.test_phase_a',
            'quant.test_evaluate_phase_a_real_data',
            'quant.test_analyze_phase_a_results',
            'quant.test_decide_phase_a_tuning',
            'quant.test_run_phase_a_threshold_sweep',
            'quant.test_freeze_phase_a_baseline',
        ];
        $python = new Process($pythonCommand, base_path(), [
            'PYTHONPYCACHEPREFIX' => '/tmp',
            'XDG_CACHE_HOME' => '/tmp',
            'MPLCONFIGDIR' => '/tmp/matplotlib',
        ]);
        $python->setTimeout(600);
        $python->run();

        $phpCommand = [
            'php',
            'artisan',
            'test',
            'tests/Unit/BacktestServiceTest.php',
            'tests/Feature/EvaluationReportTest.php',
            'tests/Unit/SentimentComparisonServiceTest.php',
            'tests/Unit/MacroRegulatorySignalServiceTest.php',
        ];
        $php = new Process($phpCommand, base_path());
        $php->setTimeout(600);
        $php->run();

        return [
            'python' => [
                'status' => $python->isSuccessful() ? 'passed' : 'failed',
                'command' => implode(' ', $pythonCommand),
                'summary' => trim($python->getOutput() ?: $python->getErrorOutput()),
            ],
            'php' => [
                'status' => $php->isSuccessful() ? 'passed' : 'failed',
                'command' => implode(' ', $phpCommand),
                'summary' => trim($php->getOutput() ?: $php->getErrorOutput()),
            ],
        ];
    }

    protected function determineCloseoutStatus(
        array $baseline,
        array $ojk,
        array $macro,
        array $tests
    ): array {
        $blocking = [];
        $hardBlocking = [];
        $notes = [];

        $baselineStatus = (string) ($baseline['baseline_status'] ?? 'draft');
        $readiness = (string) ($baseline['readiness_status'] ?? 'partially_ready');
        $strictDecision = (string) ($baseline['strict_mode_decision_code'] ?? '');
        $strictFinal = in_array($strictDecision, ['strict_default_yes', 'strict_default_no'], true)
            || $strictDecision === '';

        if (! ($baseline['available'] ?? false)) {
            $blocking[] = 'Frozen baseline belum tersedia.';
        }
        if ($baselineStatus === 'draft') {
            $blocking[] = 'Baseline Phase A masih draft dan belum layak dijadikan baseline operasional.';
        } elseif ($baselineStatus === 'provisional') {
            $notes[] = 'Baseline Phase A masih provisional.';
        }
        if (! $strictFinal) {
            $blocking[] = 'Strict mode belum final karena masih subset-only atau belum terdefinisi.';
        }
        if (($ojk['error'] ?? null) !== null) {
            $hardBlocking[] = 'Gagal membaca backfill historis OJK: '.$ojk['error'];
        } elseif (! ($ojk['ready'] ?? false)) {
            $blocking[] = 'Backfill historis OJK belum cukup untuk dianggap siap close-out.';
        } elseif ($ojk['neutral_only'] ?? false) {
            $notes[] = 'Artikel OJK historis masih neutral-only, sehingga sistem bergantung pada moderation layer, bukan arah sentimen langsung.';
        }
        if (($macro['error'] ?? null) !== null) {
            $hardBlocking[] = 'Macro regulatory signal tidak bisa dievaluasi: '.$macro['error'];
        } elseif (! ($macro['ready'] ?? false)) {
            $blocking[] = 'Macro regulatory signal belum aktif atau belum bisa dievaluasi.';
        }

        $pythonStatus = $tests['python']['status'] ?? 'skipped';
        $phpStatus = $tests['php']['status'] ?? 'skipped';
        if ($pythonStatus === 'failed' || $phpStatus === 'failed') {
            $hardBlocking[] = 'Test suite inti gagal.';
        } elseif ($pythonStatus === 'skipped' || $phpStatus === 'skipped') {
            $notes[] = 'Test suite inti tidak dijalankan pada closeout ini.';
        }

        if (! empty($hardBlocking)) {
            return [
                'status' => 'blocked',
                'reason' => 'Close-out diblokir oleh kegagalan verifikasi inti atau inspeksi runtime.',
                'blocking_items' => array_merge($hardBlocking, $blocking),
                'notes' => $notes,
            ];
        }

        if (empty($blocking) && $baselineStatus === 'final' && $readiness === 'ready' && $pythonStatus === 'passed' && $phpStatus === 'passed') {
            return [
                'status' => 'closed',
                'reason' => 'Baseline final, macro regulatory moderation, backfill OJK, dan test inti sudah selaras.',
                'blocking_items' => [],
                'notes' => $notes,
            ];
        }

        if (empty($blocking)) {
            return [
                'status' => 'closed_with_notes',
                'reason' => 'Phase A bisa dianggap selesai operasional, tetapi masih ada catatan non-blocking.',
                'blocking_items' => [],
                'notes' => $notes,
            ];
        }

        return [
            'status' => 'partially_ready',
            'reason' => 'Close-out belum penuh karena masih ada blocker operasional yang jelas.',
            'blocking_items' => $blocking,
            'notes' => $notes,
        ];
    }

    protected function buildReport(
        array $baseline,
        array $ojk,
        array $macro,
        array $tests,
        array $closeout
    ): string {
        $lines = [
            'Phase A Closeout Report',
            '======================',
            '',
            'Final status:',
            '- Status: '.$closeout['status'],
            '- Reason: '.$closeout['reason'],
            '',
            'Baseline:',
            '- Available: '.(($baseline['available'] ?? false) ? 'yes' : 'no'),
            '- Source: '.($baseline['source_path'] ?? 'n/a'),
            '- Baseline status: '.($baseline['baseline_status'] ?? 'draft'),
            '- Readiness status: '.($baseline['readiness_status'] ?? 'partially_ready'),
            '- Default threshold: '.($baseline['default_volume_spike_threshold'] ?? 2.0),
            '- Strict mode default: '.(($baseline['strict_mode_default'] ?? false) ? 'true' : 'false'),
            '- Adaptive threshold enabled: '.(($baseline['adaptive_threshold_enabled'] ?? false) ? 'true' : 'false'),
            '- Group override count: '.($baseline['group_override_count'] ?? 0),
            '',
            'OJK backfill:',
            '- Ready: '.(($ojk['ready'] ?? false) ? 'yes' : 'no'),
            '- Available: '.(($ojk['available'] ?? true) ? 'yes' : 'no'),
            '- Article count: '.($ojk['article_count'] ?? 0),
            '- Neutral article count: '.($ojk['neutral_article_count'] ?? 0),
            '- Neutral only: '.(($ojk['neutral_only'] ?? false) ? 'yes' : 'no'),
            '- Oldest published_at: '.($ojk['oldest_published_at'] ?? 'n/a'),
            '- Newest published_at: '.($ojk['newest_published_at'] ?? 'n/a'),
            '- Error: '.($ojk['error'] ?? 'none'),
            '',
            'Macro regulatory signal:',
            '- Feature flag enabled: '.(($macro['feature_flag_enabled'] ?? false) ? 'yes' : 'no'),
            '- Ready: '.(($macro['ready'] ?? false) ? 'yes' : 'no'),
            '- Neutral-only handled: '.(($macro['neutral_only_handled'] ?? false) ? 'yes' : 'no'),
            '- Attention regime: '.($macro['signal']['attention_regime'] ?? 'n/a'),
            '- Confidence multiplier: '.($macro['signal']['confidence_multiplier'] ?? 'n/a'),
            '- Narrative: '.($macro['signal']['narrative'] ?? 'n/a'),
            '- Error: '.($macro['error'] ?? 'none'),
            '',
            'Core tests:',
            '- Python: '.($tests['python']['status'] ?? 'unknown'),
            '- PHP: '.($tests['php']['status'] ?? 'unknown'),
        ];

        if (! empty($closeout['blocking_items'])) {
            $lines[] = '';
            $lines[] = 'Blocking items:';
            foreach ($closeout['blocking_items'] as $item) {
                $lines[] = '- '.$item;
            }
        }

        if (! empty($closeout['notes'])) {
            $lines[] = '';
            $lines[] = 'Notes:';
            foreach ($closeout['notes'] as $item) {
                $lines[] = '- '.$item;
            }
        }

        if (! empty($baseline['warnings'])) {
            $lines[] = '';
            $lines[] = 'Baseline warnings:';
            foreach ($baseline['warnings'] as $item) {
                $lines[] = '- '.$item;
            }
        }

        return implode("\n", $lines)."\n";
    }
}
