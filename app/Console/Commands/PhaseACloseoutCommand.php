<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\Analytics\MacroRegulatorySignalService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
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

        $mysqlStatus = $this->inspectMysqlConnectivity();
        $ojkStatus = $this->inspectOjkBackfill($mysqlStatus);
        $macroStatus = $this->inspectMacroSignal($macroRegulatorySignalService, $mysqlStatus);
        $testsStatus = $this->option('skip-tests')
            ? $this->skippedTestsStatus()
            : $this->runCoreTests();
        $runtimeDiagnostics = $this->buildRuntimeDiagnostics($mysqlStatus, $ojkStatus, $macroStatus);

        $closeout = $this->determineCloseoutStatus(
            $baselineStatus,
            $ojkStatus,
            $macroStatus,
            $testsStatus,
            $runtimeDiagnostics
        );
        $reportText = $this->buildReport(
            $baselineStatus,
            $mysqlStatus,
            $ojkStatus,
            $macroStatus,
            $testsStatus,
            $runtimeDiagnostics,
            $closeout
        );
        $runtimeDiagnosticsPayload = $this->buildRuntimeDiagnosticsPayload($runtimeDiagnostics, $closeout);
        $runtimeDiagnosticsText = $this->buildRuntimeDiagnosticsReport($runtimeDiagnosticsPayload);

        $reportPath = $outputDir.'/phase_a_closeout_report.txt';
        file_put_contents($reportPath, $reportText);

        $statusPayload = [
            'generated_at' => now()->toIso8601String(),
            'status' => $closeout['status'],
            'closeout_status' => $closeout['status'],
            'reason' => $closeout['reason'],
            'runtime_status' => $runtimeDiagnostics['runtime_status'],
            'ojk_article_count' => $ojkStatus['article_count'] ?? 0,
            'ojk_backfill_status' => $ojkStatus['check_status'] ?? 'unknown',
            'macro_runtime_status' => $macroStatus['check_status'] ?? 'unknown',
            'blocker_reason' => $closeout['blocker_reason'],
            'next_action' => $closeout['next_action'],
            'blocking_items' => $closeout['blocking_items'],
            'blocker_reasons' => $closeout['blocker_reasons'],
            'notes' => $closeout['notes'],
            'baseline' => $baselineStatus,
            'mysql_connectivity' => $mysqlStatus,
            'ojk_backfill' => $ojkStatus,
            'macro_regulatory_signal' => $macroStatus,
            'tests' => $testsStatus,
        ];

        $statusPath = $outputDir.'/phase_a_closeout_status.json';
        file_put_contents(
            $statusPath,
            json_encode($statusPayload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );

        $runtimeDiagnosticsPath = $outputDir.'/phase_a_runtime_diagnostics.json';
        file_put_contents(
            $runtimeDiagnosticsPath,
            json_encode($runtimeDiagnosticsPayload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );

        $runtimeDiagnosticsReportPath = $outputDir.'/phase_a_runtime_diagnostics.txt';
        file_put_contents($runtimeDiagnosticsReportPath, $runtimeDiagnosticsText);

        $this->info('Phase A closeout complete.');
        $this->line('Status: '.$closeout['status']);
        $this->line('Runtime: '.$runtimeDiagnostics['runtime_status']);
        $this->line('Reason: '.$closeout['reason']);
        $this->line('Report: '.$reportPath);
        $this->line('JSON: '.$statusPath);
        $this->line('Runtime diagnostics JSON: '.$runtimeDiagnosticsPath);
        $this->line('Runtime diagnostics report: '.$runtimeDiagnosticsReportPath);

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

    protected function inspectMysqlConnectivity(): array
    {
        $connectionName = (string) config('database.default', 'default');
        $connectionConfig = (array) config("database.connections.{$connectionName}", []);

        try {
            $connection = DB::connection($connectionName);
            $connection->getPdo();
            $connection->select('select 1 as health_check');

            return [
                'ok' => true,
                'status' => 'ok',
                'connection_name' => $connectionName,
                'driver' => $connectionConfig['driver'] ?? null,
                'host' => $connectionConfig['host'] ?? null,
                'port' => $connectionConfig['port'] ?? null,
                'database' => $connectionConfig['database'] ?? null,
                'error' => null,
                'next_action' => 'none',
            ];
        } catch (\Throwable $e) {
            return [
                'ok' => false,
                'status' => 'blocked_mysql',
                'connection_name' => $connectionName,
                'driver' => $connectionConfig['driver'] ?? null,
                'host' => $connectionConfig['host'] ?? null,
                'port' => $connectionConfig['port'] ?? null,
                'database' => $connectionConfig['database'] ?? null,
                'error' => $e->getMessage(),
                'next_action' => 'Periksa DB default di .env, pastikan MySQL aktif, lalu rerun php artisan phase-a:closeout.',
            ];
        }
    }

    protected function inspectOjkBackfill(array $mysqlStatus): array
    {
        $minCount = (int) config('analytics.phase_a_closeout.min_ojk_article_count', 5);
        $minHistoryDays = (int) config('analytics.phase_a_closeout.min_historical_days', 30);

        if (! ($mysqlStatus['ok'] ?? false)) {
            return [
                'available' => false,
                'ready' => false,
                'check_status' => 'mysql_blocked',
                'blocker_reason' => 'mysql_connectivity_failed',
                'article_count' => 0,
                'neutral_article_count' => 0,
                'neutral_only' => false,
                'oldest_published_at' => null,
                'newest_published_at' => null,
                'min_article_count_required' => $minCount,
                'min_history_days_required' => $minHistoryDays,
                'error' => $mysqlStatus['error'] ?? 'MySQL connection unavailable.',
                'next_action' => 'Perbaiki koneksi MySQL dulu sebelum mengecek OJK backfill.',
            ];
        }

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
            $checkStatus = 'ready';
            $blockerReason = null;
            $nextAction = 'none';

            if ($count <= 0) {
                $checkStatus = 'empty';
                $blockerReason = 'ojk_backfill_empty';
                $from = now()->subMonths(3)->startOfMonth()->toDateString();
                $to = now()->toDateString();
                $nextAction = "Jalankan php artisan news:fetch-ojk --backfill --from={$from} --to={$to} lalu rerun php artisan phase-a:closeout.";
            } elseif ($count < $minCount) {
                $checkStatus = 'insufficient_articles';
                $blockerReason = 'ojk_backfill_insufficient_articles';
                $from = now()->subMonths(3)->startOfMonth()->toDateString();
                $to = now()->toDateString();
                $nextAction = "Tambahkan artikel OJK historis dengan php artisan news:fetch-ojk --backfill --from={$from} --to={$to}, lalu rerun php artisan phase-a:closeout.";
            } elseif (! $hasHistoryCoverage) {
                $checkStatus = 'insufficient_history';
                $blockerReason = 'ojk_backfill_insufficient_history';
                $from = now()->subMonths(3)->startOfMonth()->toDateString();
                $to = now()->toDateString();
                $nextAction = "Perluas horizon backfill OJK dengan php artisan news:fetch-ojk --backfill --from={$from} --to={$to}, lalu rerun php artisan phase-a:closeout.";
            }

            return [
                'available' => true,
                'ready' => $ready,
                'check_status' => $checkStatus,
                'blocker_reason' => $blockerReason,
                'article_count' => $count,
                'neutral_article_count' => $neutralCount,
                'neutral_only' => $count > 0 && $neutralCount === $count,
                'oldest_published_at' => $oldestDate?->toDateString(),
                'newest_published_at' => $newestDate?->toDateString(),
                'min_article_count_required' => $minCount,
                'min_history_days_required' => $minHistoryDays,
                'error' => null,
                'next_action' => $nextAction,
            ];
        } catch (\Throwable $e) {
            return [
                'available' => false,
                'ready' => false,
                'check_status' => 'query_failed',
                'blocker_reason' => 'ojk_runtime_query_failed',
                'article_count' => 0,
                'neutral_article_count' => 0,
                'neutral_only' => false,
                'oldest_published_at' => null,
                'newest_published_at' => null,
                'min_article_count_required' => $minCount,
                'min_history_days_required' => $minHistoryDays,
                'error' => $e->getMessage(),
                'next_action' => 'Periksa query OJK runtime lalu rerun php artisan phase-a:closeout.',
            ];
        }
    }

    protected function inspectMacroSignal(MacroRegulatorySignalService $service, array $mysqlStatus): array
    {
        $featureFlagEnabled = (bool) config('analytics.macro_regulatory_signal.enabled', true);

        if (! ($mysqlStatus['ok'] ?? false)) {
            return [
                'feature_flag_enabled' => $featureFlagEnabled,
                'ready' => false,
                'check_status' => 'mysql_blocked',
                'blocker_reason' => 'mysql_connectivity_failed',
                'signal' => [
                    'attention_regime' => 'unavailable',
                    'confidence_multiplier' => 'n/a',
                    'narrative' => 'Macro regulatory signal belum bisa dievaluasi karena MySQL belum tersedia.',
                ],
                'neutral_only_handled' => false,
                'error' => $mysqlStatus['error'] ?? 'MySQL connection unavailable.',
                'next_action' => 'Perbaiki koneksi MySQL dulu sebelum mengecek macro regulatory runtime.',
            ];
        }

        try {
            $articles = NewsArticle::query()
                ->whereNull('stock_id')
                ->where('source_provider', 'ojk_rss')
                ->whereNotNull('published_at')
                ->where('published_at', '>=', now()->subDays(30)->startOfDay())
                ->orderBy('published_at')
                ->get();

            $signal = $service->evaluate($articles, 30, now(), $featureFlagEnabled);
            $ready = $featureFlagEnabled && is_array($signal) && array_key_exists('confidence_multiplier', $signal);
            $checkStatus = $ready ? 'ready' : ($featureFlagEnabled ? 'partial' : 'disabled');
            $blockerReason = $ready ? null : ($featureFlagEnabled ? 'macro_signal_not_usable' : 'macro_signal_disabled');
            $nextAction = $ready
                ? 'none'
                : ($featureFlagEnabled
                    ? 'Periksa evaluasi macro_regulatory_signal dan artikel OJK terbaru, lalu rerun php artisan phase-a:closeout.'
                    : 'Aktifkan analytics.macro_regulatory_signal.enabled jika fitur ini wajib untuk closeout.');

            return [
                'feature_flag_enabled' => $featureFlagEnabled,
                'ready' => $ready,
                'check_status' => $checkStatus,
                'blocker_reason' => $blockerReason,
                'signal' => $signal,
                'neutral_only_handled' => $featureFlagEnabled
                    && ($signal['active'] ?? false)
                    && array_key_exists('confidence_multiplier', $signal),
                'error' => null,
                'next_action' => $nextAction,
            ];
        } catch (\Throwable $e) {
            return [
                'feature_flag_enabled' => $featureFlagEnabled,
                'ready' => false,
                'check_status' => 'query_failed',
                'blocker_reason' => 'macro_runtime_query_failed',
                'signal' => [
                    'attention_regime' => 'unavailable',
                    'confidence_multiplier' => 'n/a',
                    'narrative' => 'Macro regulatory signal tidak bisa dievaluasi karena akses database gagal.',
                ],
                'neutral_only_handled' => false,
                'error' => $e->getMessage(),
                'next_action' => 'Periksa query runtime macro_regulatory_signal lalu rerun php artisan phase-a:closeout.',
            ];
        }
    }

    protected function buildRuntimeDiagnostics(
        array $mysqlStatus,
        array $ojkStatus,
        array $macroStatus
    ): array {
        if (! ($mysqlStatus['ok'] ?? false)) {
            return [
                'runtime_status' => 'runtime_blocked_mysql',
                'mysql_connectivity' => $mysqlStatus,
                'ojk_runtime_check' => $ojkStatus,
                'macro_regulatory_runtime_check' => $macroStatus,
                'blocker_reason' => 'mysql_connectivity_failed',
                'next_action' => $mysqlStatus['next_action'] ?? 'Perbaiki koneksi MySQL lalu rerun closeout.',
            ];
        }

        if (($ojkStatus['ready'] ?? false) !== true) {
            return [
                'runtime_status' => 'runtime_blocked_ojk',
                'mysql_connectivity' => $mysqlStatus,
                'ojk_runtime_check' => $ojkStatus,
                'macro_regulatory_runtime_check' => $macroStatus,
                'blocker_reason' => $ojkStatus['blocker_reason'] ?? 'ojk_backfill_not_ready',
                'next_action' => $ojkStatus['next_action'] ?? 'Isi OJK backfill lalu rerun closeout.',
            ];
        }

        if (($macroStatus['ready'] ?? false) !== true) {
            return [
                'runtime_status' => 'runtime_partial',
                'mysql_connectivity' => $mysqlStatus,
                'ojk_runtime_check' => $ojkStatus,
                'macro_regulatory_runtime_check' => $macroStatus,
                'blocker_reason' => $macroStatus['blocker_reason'] ?? 'macro_runtime_not_ready',
                'next_action' => $macroStatus['next_action'] ?? 'Periksa macro runtime lalu rerun closeout.',
            ];
        }

        return [
            'runtime_status' => 'runtime_ok',
            'mysql_connectivity' => $mysqlStatus,
            'ojk_runtime_check' => $ojkStatus,
            'macro_regulatory_runtime_check' => $macroStatus,
            'blocker_reason' => null,
            'next_action' => 'Runtime Phase A sehat. Jika closeout masih blocked, fokus ke test suite atau baseline gating.',
        ];
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
        array $tests,
        array $runtimeDiagnostics
    ): array {
        $blocking = [];
        $hardBlocking = [];
        $notes = [];
        $blockerReasons = [];

        $baselineStatus = (string) ($baseline['baseline_status'] ?? 'draft');
        $readiness = (string) ($baseline['readiness_status'] ?? 'partially_ready');
        $strictDecision = (string) ($baseline['strict_mode_decision_code'] ?? '');
        $strictFinal = in_array($strictDecision, ['strict_default_yes', 'strict_default_no'], true)
            || $strictDecision === '';

        if (! ($baseline['available'] ?? false)) {
            $blocking[] = 'Frozen baseline belum tersedia.';
            $blockerReasons[] = 'baseline_missing';
        }
        if ($baselineStatus === 'draft') {
            $blocking[] = 'Baseline Phase A masih draft dan belum layak dijadikan baseline operasional.';
        } elseif ($baselineStatus === 'provisional') {
            $notes[] = 'Baseline Phase A masih provisional.';
        }
        if (! $strictFinal) {
            $blocking[] = 'Strict mode belum final karena masih subset-only atau belum terdefinisi.';
            $blockerReasons[] = 'strict_mode_not_final';
        }
        if (($ojk['error'] ?? null) !== null) {
            $hardBlocking[] = 'Gagal membaca backfill historis OJK: '.$ojk['error'];
            $blockerReasons[] = $ojk['blocker_reason'] ?? 'ojk_runtime_query_failed';
        } elseif (! ($ojk['ready'] ?? false)) {
            $blocking[] = 'Backfill historis OJK belum cukup untuk dianggap siap close-out.';
            $blockerReasons[] = $ojk['blocker_reason'] ?? 'ojk_backfill_not_ready';
        } elseif ($ojk['neutral_only'] ?? false) {
            $notes[] = 'Artikel OJK historis masih neutral-only, sehingga sistem bergantung pada moderation layer, bukan arah sentimen langsung.';
        }
        if (($macro['error'] ?? null) !== null) {
            $hardBlocking[] = 'Macro regulatory signal tidak bisa dievaluasi: '.$macro['error'];
            $blockerReasons[] = $macro['blocker_reason'] ?? 'macro_runtime_query_failed';
        } elseif (! ($macro['ready'] ?? false)) {
            $blocking[] = 'Macro regulatory signal belum aktif atau belum bisa dievaluasi.';
            $blockerReasons[] = $macro['blocker_reason'] ?? 'macro_runtime_not_ready';
        }

        $pythonStatus = $tests['python']['status'] ?? 'skipped';
        $phpStatus = $tests['php']['status'] ?? 'skipped';
        if ($pythonStatus === 'failed' || $phpStatus === 'failed') {
            $hardBlocking[] = 'Test suite inti gagal.';
            $blockerReasons[] = 'core_test_suite_failed';
        } elseif ($pythonStatus === 'skipped' || $phpStatus === 'skipped') {
            $notes[] = 'Test suite inti tidak dijalankan pada closeout ini.';
        }

        $blockerReasons = array_values(array_unique(array_filter($blockerReasons)));
        $nextAction = $this->determineCloseoutNextAction(
            $runtimeDiagnostics,
            $tests,
            $blockerReasons
        );

        if (! empty($hardBlocking)) {
            return [
                'status' => 'blocked',
                'reason' => 'Close-out diblokir oleh kegagalan verifikasi inti atau inspeksi runtime.',
                'blocking_items' => array_merge($hardBlocking, $blocking),
                'blocker_reason' => $blockerReasons[0] ?? null,
                'blocker_reasons' => $blockerReasons,
                'next_action' => $nextAction,
                'notes' => $notes,
            ];
        }

        if (empty($blocking) && $baselineStatus === 'final' && $readiness === 'ready' && $pythonStatus === 'passed' && $phpStatus === 'passed') {
            return [
                'status' => 'closed',
                'reason' => 'Baseline final, macro regulatory moderation, backfill OJK, dan test inti sudah selaras.',
                'blocking_items' => [],
                'blocker_reason' => null,
                'blocker_reasons' => [],
                'next_action' => 'none',
                'notes' => $notes,
            ];
        }

        if (empty($blocking)) {
            return [
                'status' => 'closed_with_notes',
                'reason' => 'Phase A bisa dianggap selesai operasional, tetapi masih ada catatan non-blocking.',
                'blocking_items' => [],
                'blocker_reason' => null,
                'blocker_reasons' => [],
                'next_action' => 'none',
                'notes' => $notes,
            ];
        }

        return [
            'status' => 'partially_ready',
            'reason' => 'Close-out belum penuh karena masih ada blocker operasional yang jelas.',
            'blocking_items' => $blocking,
            'blocker_reason' => $blockerReasons[0] ?? null,
            'blocker_reasons' => $blockerReasons,
            'next_action' => $nextAction,
            'notes' => $notes,
        ];
    }

    protected function determineCloseoutNextAction(
        array $runtimeDiagnostics,
        array $tests,
        array $blockerReasons
    ): string {
        $actions = [];

        if (($runtimeDiagnostics['runtime_status'] ?? null) === 'runtime_blocked_mysql') {
            $actions[] = $runtimeDiagnostics['next_action'] ?? 'Perbaiki koneksi MySQL lalu rerun closeout.';
        } elseif (($runtimeDiagnostics['runtime_status'] ?? null) === 'runtime_blocked_ojk') {
            $actions[] = $runtimeDiagnostics['next_action'] ?? 'Isi OJK backfill lalu rerun closeout.';
        } elseif (($runtimeDiagnostics['runtime_status'] ?? null) === 'runtime_partial') {
            $actions[] = $runtimeDiagnostics['next_action'] ?? 'Periksa runtime macro lalu rerun closeout.';
        }

        if (($tests['python']['status'] ?? null) === 'failed' || ($tests['php']['status'] ?? null) === 'failed') {
            $actions[] = 'Perbaiki test suite inti yang gagal, lalu rerun php artisan phase-a:closeout.';
        }

        if (empty($actions) && ! empty($blockerReasons)) {
            $actions[] = 'Selesaikan blocker closeout yang tersisa lalu rerun php artisan phase-a:closeout.';
        }

        return implode(' ', array_values(array_unique(array_filter($actions)))) ?: 'none';
    }

    protected function buildRuntimeDiagnosticsPayload(array $runtimeDiagnostics, array $closeout): array
    {
        return [
            'generated_at' => now()->toIso8601String(),
            'runtime_status' => $runtimeDiagnostics['runtime_status'],
            'ojk_article_count' => $runtimeDiagnostics['ojk_runtime_check']['article_count'] ?? 0,
            'ojk_backfill_status' => $runtimeDiagnostics['ojk_runtime_check']['check_status'] ?? 'unknown',
            'macro_runtime_status' => $runtimeDiagnostics['macro_regulatory_runtime_check']['check_status'] ?? 'unknown',
            'mysql_connectivity' => $runtimeDiagnostics['mysql_connectivity'] ?? null,
            'ojk_runtime_check' => $runtimeDiagnostics['ojk_runtime_check'] ?? null,
            'macro_regulatory_runtime_check' => $runtimeDiagnostics['macro_regulatory_runtime_check'] ?? null,
            'closeout_status' => $closeout['status'],
            'blocker_reason' => $closeout['blocker_reason'] ?? $runtimeDiagnostics['blocker_reason'],
            'blocker_reasons' => $closeout['blocker_reasons'] ?? [],
            'next_action' => $closeout['next_action'] ?? $runtimeDiagnostics['next_action'],
        ];
    }

    protected function buildRuntimeDiagnosticsReport(array $payload): string
    {
        $mysql = (array) ($payload['mysql_connectivity'] ?? []);
        $ojk = (array) ($payload['ojk_runtime_check'] ?? []);
        $macro = (array) ($payload['macro_regulatory_runtime_check'] ?? []);

        $lines = [
            'Phase A Runtime Diagnostics',
            '===========================',
            '',
            '- runtime_status='.$payload['runtime_status'],
            '- closeout_status='.$payload['closeout_status'],
            '- ojk_article_count='.(string) ($payload['ojk_article_count'] ?? 0),
            '- ojk_backfill_status='.($payload['ojk_backfill_status'] ?? 'unknown'),
            '- macro_runtime_status='.($payload['macro_runtime_status'] ?? 'unknown'),
            '- blocker_reason='.($payload['blocker_reason'] ?? 'none'),
            '- next_action='.($payload['next_action'] ?? 'none'),
            '',
            'MySQL connectivity:',
            '- status='.($mysql['status'] ?? 'unknown'),
            '- connection_name='.($mysql['connection_name'] ?? 'n/a'),
            '- driver='.($mysql['driver'] ?? 'n/a'),
            '- host='.($mysql['host'] ?? 'n/a'),
            '- port='.(string) ($mysql['port'] ?? 'n/a'),
            '- database='.($mysql['database'] ?? 'n/a'),
            '- error='.($mysql['error'] ?? 'none'),
            '',
            'OJK runtime check:',
            '- status='.($ojk['check_status'] ?? 'unknown'),
            '- ready='.(($ojk['ready'] ?? false) ? 'yes' : 'no'),
            '- article_count='.(string) ($ojk['article_count'] ?? 0),
            '- oldest_published_at='.($ojk['oldest_published_at'] ?? 'n/a'),
            '- newest_published_at='.($ojk['newest_published_at'] ?? 'n/a'),
            '- blocker_reason='.($ojk['blocker_reason'] ?? 'none'),
            '- error='.($ojk['error'] ?? 'none'),
            '',
            'Macro regulatory runtime check:',
            '- status='.($macro['check_status'] ?? 'unknown'),
            '- ready='.(($macro['ready'] ?? false) ? 'yes' : 'no'),
            '- blocker_reason='.($macro['blocker_reason'] ?? 'none'),
            '- error='.($macro['error'] ?? 'none'),
        ];

        return implode("\n", $lines)."\n";
    }

    protected function buildReport(
        array $baseline,
        array $mysql,
        array $ojk,
        array $macro,
        array $tests,
        array $runtimeDiagnostics,
        array $closeout
    ): string {
        $lines = [
            'Phase A Closeout Report',
            '======================',
            '',
            'Final status:',
            '- Status: '.$closeout['status'],
            '- Reason: '.$closeout['reason'],
            '- Runtime status: '.($runtimeDiagnostics['runtime_status'] ?? 'unknown'),
            '- OJK article count: '.($ojk['article_count'] ?? 0),
            '- OJK backfill status: '.($ojk['check_status'] ?? 'unknown'),
            '- Macro runtime status: '.($macro['check_status'] ?? 'unknown'),
            '- Blocker reason: '.($closeout['blocker_reason'] ?? 'none'),
            '- Next action: '.($closeout['next_action'] ?? 'none'),
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
            'MySQL connectivity:',
            '- Status: '.($mysql['status'] ?? 'unknown'),
            '- Connection name: '.($mysql['connection_name'] ?? 'n/a'),
            '- Driver: '.($mysql['driver'] ?? 'n/a'),
            '- Host: '.($mysql['host'] ?? 'n/a'),
            '- Port: '.($mysql['port'] ?? 'n/a'),
            '- Database: '.($mysql['database'] ?? 'n/a'),
            '- Error: '.($mysql['error'] ?? 'none'),
            '',
            'OJK backfill:',
            '- Ready: '.(($ojk['ready'] ?? false) ? 'yes' : 'no'),
            '- Available: '.(($ojk['available'] ?? true) ? 'yes' : 'no'),
            '- Check status: '.($ojk['check_status'] ?? 'unknown'),
            '- Article count: '.($ojk['article_count'] ?? 0),
            '- Neutral article count: '.($ojk['neutral_article_count'] ?? 0),
            '- Neutral only: '.(($ojk['neutral_only'] ?? false) ? 'yes' : 'no'),
            '- Oldest published_at: '.($ojk['oldest_published_at'] ?? 'n/a'),
            '- Newest published_at: '.($ojk['newest_published_at'] ?? 'n/a'),
            '- Blocker reason: '.($ojk['blocker_reason'] ?? 'none'),
            '- Error: '.($ojk['error'] ?? 'none'),
            '',
            'Macro regulatory signal:',
            '- Feature flag enabled: '.(($macro['feature_flag_enabled'] ?? false) ? 'yes' : 'no'),
            '- Ready: '.(($macro['ready'] ?? false) ? 'yes' : 'no'),
            '- Check status: '.($macro['check_status'] ?? 'unknown'),
            '- Neutral-only handled: '.(($macro['neutral_only_handled'] ?? false) ? 'yes' : 'no'),
            '- Attention regime: '.($macro['signal']['attention_regime'] ?? 'n/a'),
            '- Confidence multiplier: '.($macro['signal']['confidence_multiplier'] ?? 'n/a'),
            '- Narrative: '.($macro['signal']['narrative'] ?? 'n/a'),
            '- Blocker reason: '.($macro['blocker_reason'] ?? 'none'),
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
