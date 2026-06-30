<?php

namespace Tests\Unit;

use App\Services\Research\ResearchArtifactService;
use InvalidArgumentException;
use Tests\TestCase;

class ResearchArtifactServiceTest extends TestCase
{
    public function test_loads_valid_example_artifact(): void
    {
        $service = new ResearchArtifactService;
        $artifact = $service->load(
            $service->examplePath('walk_forward_bumi_v1.json'),
            'walk_forward',
            'BUMI'
        );

        $this->assertSame('walk_forward_v1', $artifact['schema_version']);
        $this->assertSame('walk_forward', $artifact['artifact_type']);
        $this->assertSame('BUMI', $artifact['ticker']);
        $this->assertArrayHasKey('summary', $artifact);
        $this->assertSame('example', $artifact['quality']['status']);
    }

    public function test_available_returns_unavailable_payload_for_missing_file(): void
    {
        $service = new ResearchArtifactService;
        $result = $service->available(storage_path('app/trading_research/examples/missing.json'), 'walk_forward', 'BUMI');

        $this->assertFalse($result['available']);
        $this->assertNull($result['artifact']);
        $this->assertStringContainsString('not found', $result['message']);
    }

    public function test_rejects_unexpected_schema_version(): void
    {
        $path = tempnam(sys_get_temp_dir(), 'artifact_');
        file_put_contents($path, json_encode([
            'schema_version' => 'walk_forward_v999',
            'artifact_type' => 'walk_forward',
            'ticker' => 'BUMI',
            'generated_at' => '2026-07-01T00:00:00+07:00',
            'quality' => [],
        ]));

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Unsupported schema');

        (new ResearchArtifactService)->load($path, 'walk_forward', 'BUMI');
    }

    public function test_latest_selects_newest_valid_artifact_for_type_and_ticker(): void
    {
        $directory = sys_get_temp_dir().'/research_artifacts_'.uniqid();
        mkdir($directory, 0777, true);

        file_put_contents($directory.'/old.json', json_encode($this->artifact('2026-07-01T00:00:00+07:00')));
        file_put_contents($directory.'/new.json', json_encode($this->artifact('2026-07-02T00:00:00+07:00')));
        file_put_contents($directory.'/wrong_ticker.json', json_encode(array_merge($this->artifact('2026-07-03T00:00:00+07:00'), ['ticker' => 'DEWA'])));

        $result = (new ResearchArtifactService)->latest('walk_forward', 'BUMI', $directory);

        $this->assertTrue($result['available']);
        $this->assertStringEndsWith('new.json', $result['path']);
        $this->assertSame('2026-07-02T00:00:00+07:00', $result['artifact']['generated_at']);
    }

    public function test_latest_returns_unavailable_when_directory_has_no_valid_artifact(): void
    {
        $directory = sys_get_temp_dir().'/research_artifacts_empty_'.uniqid();
        mkdir($directory, 0777, true);

        $result = (new ResearchArtifactService)->latest('walk_forward', 'BUMI', $directory);

        $this->assertFalse($result['available']);
        $this->assertNull($result['artifact']);
        $this->assertStringContainsString('No valid walk_forward artifact', $result['message']);
    }

    private function artifact(string $generatedAt): array
    {
        return [
            'schema_version' => 'walk_forward_v1',
            'artifact_type' => 'walk_forward',
            'ticker' => 'BUMI',
            'generated_at' => $generatedAt,
            'folds' => [],
            'summary' => [],
            'quality' => ['status' => 'test'],
        ];
    }
}
