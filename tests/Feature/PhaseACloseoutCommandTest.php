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

        $payload = json_decode((string) file_get_contents(base_path('output/phase_a_closeout_status.json')), true);
        $this->assertContains($payload['status'], ['closed_with_notes', 'partially_ready']);
        $this->assertArrayHasKey('macro_regulatory_signal', $payload);
        $this->assertArrayHasKey('baseline', $payload);
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

            $this->assertSame('blocked', $payload['status']);
            $this->assertNotEmpty($payload['blocking_items']);
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
}
