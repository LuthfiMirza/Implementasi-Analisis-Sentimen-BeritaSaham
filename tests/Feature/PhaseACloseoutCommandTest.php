<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class PhaseACloseoutCommandTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        File::delete(base_path('output/phase_a_closeout_report.txt'));
        File::delete(base_path('output/phase_a_closeout_status.json'));
        File::delete(base_path('output/phase_a_runtime_diagnostics.txt'));
        File::delete(base_path('output/phase_a_runtime_diagnostics.json'));
        File::delete(base_path('output/phase_a_baseline_final.json'));

        parent::tearDown();
    }

    public function test_closeout_command_generates_report_and_status_files(): void
    {
        config(['analytics.macro_regulatory_signal.enabled' => true]);

        File::ensureDirectoryExists(base_path('output'));
        File::put(
            base_path('output/phase_a_baseline_final.json'),
            json_encode([
                'baseline_status' => 'provisional',
                'readiness_status' => 'partially_ready',
                'default_volume_spike_threshold' => 2.0,
                'strict_mode_default' => false,
                'adaptive_threshold_enabled' => false,
                'group_threshold_overrides' => [],
                'strict_mode_decision_code' => 'strict_default_no',
                'warnings' => [],
            ], JSON_PRETTY_PRINT)
        );

        for ($i = 0; $i < 6; $i++) {
            NewsArticle::factory()->create([
                'stock_id' => null,
                'source_provider' => 'ojk_rss',
                'sentiment_label' => 'neutral',
                'published_at' => Carbon::now()->subDays(45 - $i),
                'title' => 'OJK penguatan pasar modal '.$i,
                'final_quality_score' => 0.75,
            ]);
        }

        $this->artisan('phase-a:closeout --skip-tests --skip-freeze-baseline')
            ->assertSuccessful();

        $this->assertFileExists(base_path('output/phase_a_closeout_report.txt'));
        $this->assertFileExists(base_path('output/phase_a_closeout_status.json'));
        $this->assertFileExists(base_path('output/phase_a_runtime_diagnostics.txt'));
        $this->assertFileExists(base_path('output/phase_a_runtime_diagnostics.json'));

        $payload = json_decode((string) file_get_contents(base_path('output/phase_a_closeout_status.json')), true);
        $this->assertContains($payload['status'], ['closed_with_notes', 'partially_ready']);
        $this->assertArrayHasKey('macro_regulatory_signal', $payload);
        $this->assertArrayHasKey('baseline', $payload);
        $this->assertArrayHasKey('runtime_status', $payload);
        $this->assertArrayHasKey('ojk_article_count', $payload);
        $this->assertArrayHasKey('ojk_backfill_status', $payload);
        $this->assertArrayHasKey('macro_runtime_status', $payload);
        $this->assertSame('runtime_ok', $payload['runtime_status']);

        $runtime = json_decode((string) file_get_contents(base_path('output/phase_a_runtime_diagnostics.json')), true);
        $this->assertSame('runtime_ok', $runtime['runtime_status']);
        $this->assertSame($payload['status'], $runtime['closeout_status']);
        $this->assertSame(6, $runtime['ojk_article_count']);
        $this->assertSame('ready', $runtime['ojk_backfill_status']);
        $this->assertSame('ready', $runtime['macro_runtime_status']);
        $this->assertArrayHasKey('mysql_connectivity', $runtime);
        $this->assertArrayHasKey('ojk_runtime_check', $runtime);
        $this->assertArrayHasKey('macro_regulatory_runtime_check', $runtime);
    }

    public function test_closeout_command_handles_database_unavailable_without_crashing(): void
    {
        File::ensureDirectoryExists(base_path('output'));
        File::put(
            base_path('output/phase_a_baseline_final.json'),
            json_encode([
                'baseline_status' => 'provisional',
                'readiness_status' => 'partially_ready',
                'default_volume_spike_threshold' => 2.0,
                'strict_mode_default' => false,
                'adaptive_threshold_enabled' => false,
                'group_threshold_overrides' => [],
                'strict_mode_decision_code' => 'strict_default_no',
                'warnings' => [],
            ], JSON_PRETTY_PRINT)
        );

        $originalDefault = config('database.default');
        $originalMysql = config('database.connections.mysql');

        try {
            config([
                'database.default' => 'mysql',
                'database.connections.mysql.host' => '127.0.0.1',
                'database.connections.mysql.port' => 3306,
                'database.connections.mysql.database' => 'sentimena_dashboard',
                'database.connections.mysql.username' => 'invalid',
                'database.connections.mysql.password' => 'invalid',
            ]);

            DB::purge('mysql');

            $this->artisan('phase-a:closeout --skip-tests --skip-freeze-baseline')
                ->assertSuccessful();

            $payload = json_decode((string) file_get_contents(base_path('output/phase_a_closeout_status.json')), true);
            $runtime = json_decode((string) file_get_contents(base_path('output/phase_a_runtime_diagnostics.json')), true);

            $this->assertSame('blocked', $payload['status']);
            $this->assertNotEmpty($payload['blocking_items']);
            $this->assertSame('runtime_blocked_mysql', $payload['runtime_status']);
            $this->assertSame('runtime_blocked_mysql', $runtime['runtime_status']);
            $this->assertSame('mysql_blocked', $runtime['ojk_backfill_status']);
            $this->assertSame('mysql_blocked', $runtime['macro_runtime_status']);
            $this->assertSame('mysql_connectivity_failed', $runtime['blocker_reason']);
            $this->assertStringContainsString(
                'Gagal membaca backfill historis OJK',
                implode(' | ', $payload['blocking_items'])
            );
            $this->assertStringContainsString(
                'Macro regulatory signal tidak bisa dievaluasi',
                implode(' | ', $payload['blocking_items'])
            );
        } finally {
            config([
                'database.default' => $originalDefault,
                'database.connections.mysql' => $originalMysql,
            ]);

            DB::purge('mysql');
            DB::setDefaultConnection($originalDefault);
        }
    }

    public function test_closeout_command_marks_runtime_blocked_ojk_when_backfill_is_empty(): void
    {
        File::ensureDirectoryExists(base_path('output'));
        File::put(
            base_path('output/phase_a_baseline_final.json'),
            json_encode([
                'baseline_status' => 'provisional',
                'readiness_status' => 'partially_ready',
                'default_volume_spike_threshold' => 2.0,
                'strict_mode_default' => false,
                'adaptive_threshold_enabled' => false,
                'group_threshold_overrides' => [],
                'strict_mode_decision_code' => 'strict_default_no',
                'warnings' => [],
            ], JSON_PRETTY_PRINT)
        );

        $this->artisan('phase-a:closeout --skip-tests --skip-freeze-baseline')
            ->assertSuccessful();

        $payload = json_decode((string) file_get_contents(base_path('output/phase_a_closeout_status.json')), true);
        $runtime = json_decode((string) file_get_contents(base_path('output/phase_a_runtime_diagnostics.json')), true);

        $this->assertSame('runtime_blocked_ojk', $payload['runtime_status']);
        $this->assertSame('runtime_blocked_ojk', $runtime['runtime_status']);
        $this->assertSame(0, $runtime['ojk_article_count']);
        $this->assertSame('empty', $runtime['ojk_backfill_status']);
        $this->assertSame('ojk_backfill_empty', $runtime['blocker_reason']);
        $this->assertStringContainsString('news:fetch-ojk --backfill', $runtime['next_action']);
    }

    public function test_closeout_command_marks_runtime_partial_when_macro_runtime_is_disabled(): void
    {
        config(['analytics.macro_regulatory_signal.enabled' => false]);

        File::ensureDirectoryExists(base_path('output'));
        File::put(
            base_path('output/phase_a_baseline_final.json'),
            json_encode([
                'baseline_status' => 'provisional',
                'readiness_status' => 'partially_ready',
                'default_volume_spike_threshold' => 2.0,
                'strict_mode_default' => false,
                'adaptive_threshold_enabled' => false,
                'group_threshold_overrides' => [],
                'strict_mode_decision_code' => 'strict_default_no',
                'warnings' => [],
            ], JSON_PRETTY_PRINT)
        );

        for ($i = 0; $i < 6; $i++) {
            NewsArticle::factory()->create([
                'stock_id' => null,
                'source_provider' => 'ojk_rss',
                'sentiment_label' => 'neutral',
                'published_at' => Carbon::now()->subDays(45 - $i),
                'title' => 'OJK makro '.$i,
                'final_quality_score' => 0.75,
            ]);
        }

        $this->artisan('phase-a:closeout --skip-tests --skip-freeze-baseline')
            ->assertSuccessful();

        $payload = json_decode((string) file_get_contents(base_path('output/phase_a_closeout_status.json')), true);
        $runtime = json_decode((string) file_get_contents(base_path('output/phase_a_runtime_diagnostics.json')), true);

        $this->assertSame('runtime_partial', $payload['runtime_status']);
        $this->assertSame('runtime_partial', $runtime['runtime_status']);
        $this->assertSame('ready', $runtime['ojk_backfill_status']);
        $this->assertSame('disabled', $runtime['macro_runtime_status']);
        $this->assertSame('macro_signal_disabled', $runtime['blocker_reason']);
    }
}
