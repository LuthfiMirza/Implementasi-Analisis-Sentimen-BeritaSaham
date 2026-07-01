<?php

namespace Tests\Feature;

use App\Models\TradeResearchArtifact;
use App\Services\Research\ResearchArtifactDiscoveryService;
use App\Services\Research\ResearchArtifactRegistryService;
use App\Services\Research\ResearchArtifactValidationService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class ResearchArtifactRegistryTest extends TestCase
{
    use RefreshDatabase;

    protected string $root;

    protected function setUp(): void
    {
        parent::setUp();
        $this->root = storage_path('framework/testing/research_artifacts_'.uniqid());
        File::ensureDirectoryExists($this->root);
        config(['trading_research.allowed_roots' => [$this->root]]);
        config(['trading_research.maximum_file_size' => 1024 * 1024]);
    }

    protected function tearDown(): void
    {
        File::deleteDirectory($this->root);
        parent::tearDown();
    }

    public function test_discovery_filters_and_rejects_unsafe_paths(): void
    {
        $this->writeArtifact('BUMI_event.json', $this->artifact('BUMI', 'walk_forward_event_dataset', 'walk_forward_event_dataset_v1'));
        $this->writeArtifact('DEWA_event.json', $this->artifact('DEWA', 'walk_forward_event_dataset', 'walk_forward_event_dataset_v1'));
        File::put($this->root.'/ignore.txt', '{}');

        $service = app(ResearchArtifactDiscoveryService::class);
        $files = $service->discover($this->root, 'BUMI', 'walk_forward_event_dataset');

        $this->assertCount(1, $files);
        $this->assertStringEndsWith('BUMI_event.json', $files[0]);
        $this->expectException(\InvalidArgumentException::class);
        $service->discover($this->root.'/../outside');
    }

    public function test_validation_normalizes_research_only_and_limitations(): void
    {
        $path = $this->writeArtifact('DEWA_reentry.json', $this->reentryArtifact('DEWA', 0.46));
        $result = app(ResearchArtifactValidationService::class)->validate($path);

        $this->assertTrue($result['valid']);
        $this->assertSame('reentry_research', $result['artifact_type']);
        $this->assertSame('research_only', $result['usage_tier']);
        $this->assertFalse($result['usable_for_decision']);
        $this->assertSame('limited', $result['quality_grade']);
        $this->assertContains('high_unclassified_rate', $result['warnings']);
        $this->assertArrayHasKey('unclassified', $result['limitations']);
    }

    public function test_import_is_idempotent_and_latest_decision_does_not_fallback(): void
    {
        $path = $this->writeArtifact('BUMI_reentry.json', $this->reentryArtifact('BUMI', 0.06));
        $registry = app(ResearchArtifactRegistryService::class);

        $first = $registry->register($path, verifyDependencies: true);
        $second = $registry->register($path, verifyDependencies: true);

        $this->assertSame('imported', $first['status']);
        $this->assertSame('unchanged', $second['status']);
        $this->assertSame(1, TradeResearchArtifact::count());
        $this->assertNotNull($registry->latestValid('BUMI', 'reentry_research'));
        $this->assertNotNull($registry->latestResearchUsable('BUMI', 'reentry_research'));
        $this->assertNull($registry->latestDecisionUsable('BUMI', 'reentry_research'));
    }

    public function test_dependency_rows_store_external_and_unresolved_artifact_dependencies(): void
    {
        $path = $this->writeArtifact('BUMI_reentry.json', $this->reentryArtifact('BUMI', 0.06));
        $result = app(ResearchArtifactRegistryService::class)->register($path, verifyDependencies: true);
        $dependencies = $result['artifact']->dependencies()->pluck('resolution_status')->all();

        $this->assertTrue(collect($dependencies)->intersect(['missing_file', 'unresolved'])->isNotEmpty());
        $this->assertContains('external_source', $dependencies);
        $this->assertSame(3, $result['artifact']->dependencies()->count());
    }

    public function test_logical_identity_conflict_is_quarantined_and_not_latest(): void
    {
        $artifact = $this->reentryArtifact('BUMI', 0.06);
        $pathA = $this->writeArtifact('a.json', $artifact);
        $artifact['warnings'][] = 'changed';
        $pathB = $this->writeArtifact('b.json', $artifact);
        $registry = app(ResearchArtifactRegistryService::class);

        $registry->register($pathA);
        $conflict = $registry->register($pathB);

        $this->assertSame('conflict', $conflict['status']);
        $this->assertTrue($conflict['artifact']->is_quarantined);
        $this->assertSame(1, TradeResearchArtifact::where('is_latest', true)->count());
    }

    public function test_verify_detects_modified_file_without_changing_payload(): void
    {
        $path = $this->writeArtifact('BUMI_reentry.json', $this->reentryArtifact('BUMI', 0.06));
        $registry = app(ResearchArtifactRegistryService::class);
        $artifact = $registry->register($path)['artifact'];
        $before = File::get($path);
        File::put($path, json_encode($this->reentryArtifact('BUMI', 0.07)));

        $verify = $registry->verifyRecord($artifact->id, quarantineInvalid: true, repairLatest: true);

        $this->assertSame('checksum_mismatch', $verify['status']);
        $this->assertTrue($verify['artifact']->is_quarantined);
        $this->assertNotSame('', $before);
        $this->assertJson(File::get($path));
    }

    public function test_import_and_verify_commands_json_output_and_dry_run(): void
    {
        $this->writeArtifact('BUMI_reentry.json', $this->reentryArtifact('BUMI', 0.06));

        $this->artisan('trading-research:import-artifacts', ['--path' => $this->root, '--dry-run' => true, '--json-output' => true])->assertExitCode(0);
        $this->assertSame(0, TradeResearchArtifact::count());

        $this->artisan('trading-research:import-artifacts', ['--path' => $this->root, '--json-output' => true])->assertExitCode(0);
        $this->assertSame(1, TradeResearchArtifact::count());

        $this->artisan('trading-research:verify-artifacts', ['--json-output' => true, '--repair-latest' => true])->assertExitCode(0);
    }

    protected function writeArtifact(string $name, array $payload): string
    {
        $path = $this->root.'/'.$name;
        File::put($path, json_encode($payload, JSON_PRETTY_PRINT));
        return $path;
    }

    protected function artifact(string $ticker, string $type, string $schema): array
    {
        return [
            'schema_version' => $schema,
            'artifact_type' => $type,
            'ticker' => $ticker,
            'generated_at' => '2026-07-01T00:00:00+00:00',
            'generator_version' => 'test',
            'quality' => ['status' => 'research_only', 'event_count' => 10, 'usable_for_decision' => false],
            'warnings' => [],
            'source' => [],
        ];
    }

    protected function reentryArtifact(string $ticker, float $unclassifiedRate): array
    {
        $unclassified = (int) round($unclassifiedRate * 100);
        $ohlcv = $this->root.'/'.$ticker.'.csv';
        File::put($ohlcv, "date,open,high,low,close,volume\n2026-01-01,1,1,1,1,1\n");
        return [
            'schema_version' => 'reentry_research_v1_1',
            'artifact_type' => 'reentry_research',
            'ticker' => $ticker,
            'generated_at' => '2026-07-01T00:00:00+00:00',
            'generator_version' => 'test',
            'quality' => ['status' => 'research_only', 'usable_for_reentry_research' => true, 'usable_for_decision' => false],
            'selected' => null,
            'warnings' => ['source SL/TP research-only input'],
            'episode_accounting' => [
                'source_episode_count' => 100,
                'unclassified_count' => $unclassified,
                'unclassified_rate' => $unclassifiedRate,
                'unclassified_reasons' => ['other' => $unclassified],
            ],
            'family_quality' => [
                'atr_pullback' => ['implementation_status' => 'implemented_but_unavailable', 'coverage' => 0.0],
            ],
            'summary' => ['primary_stream' => 'after_stop'],
            'source' => [
                'episode_artifact_path' => $this->root.'/missing_episode.json',
                'episode_artifact_schema' => 'trade_episode_dataset_v1',
                'episode_artifact_checksum' => str_repeat('a', 64),
                'sl_artifact_path' => $this->root.'/missing_sl.json',
                'sl_artifact_schema' => 'sl_optimizer_v1_1',
                'sl_artifact_checksum' => str_repeat('b', 64),
                'ohlcv_path' => $ohlcv,
                'ohlcv_checksum' => hash_file('sha256', $ohlcv),
            ],
        ];
    }
}
