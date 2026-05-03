<?php

namespace Tests\Unit;

use App\Services\PaperTrading\PaperTradingLogService;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class PaperTradingLogServiceTest extends TestCase
{
    public function test_paper_trading_log_service_reads_snapshot_from_output_directory(): void
    {
        $service = $this->paperService();
        $service->ensureOutputDirectory();
        File::put($service->snapshotPath('2026-04-30'), json_encode([
            'date' => '2026-04-30',
            'reference_date' => '2026-04-29',
            'rankings' => [['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.8, 'signal' => 'candidate']],
            'model_version' => 'test-v1',
            'horizon_days' => 5,
        ]));

        $payload = $service->latestSnapshotPayload();

        // Paper trading evaluation depends on stable JSON snapshot discovery.
        $this->assertSame('2026-04-30', $payload['date']);
        $this->assertStringContainsString('output/paper_trading', $service->snapshotPath('2026-04-30'));
    }

    private function paperService(): PaperTradingLogService
    {
        return new class extends PaperTradingLogService {
            public function __construct() {}
            public function outputDirectory(): string
            {
                return base_path('storage/framework/testing/output/paper_trading');
            }
        };
    }
}
