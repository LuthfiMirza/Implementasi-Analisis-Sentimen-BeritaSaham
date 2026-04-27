<?php

namespace Tests\Unit;

use App\Services\MarketData\LiveMarketDataService;
use App\Services\PaperTrading\PaperTradingLogService;
use App\Services\Prediction\ResearchPredictionFeatureService;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class PaperTradingLogServiceTest extends TestCase
{
    protected string $tempDirectory;

    protected function setUp(): void
    {
        parent::setUp();

        $this->tempDirectory = sys_get_temp_dir().'/sentimena-paper-trading-tests-'.bin2hex(random_bytes(5));
        File::ensureDirectoryExists($this->tempDirectory);
    }

    protected function tearDown(): void
    {
        File::deleteDirectory($this->tempDirectory);

        parent::tearDown();
    }

    public function test_get_latest_snapshot_returns_data_from_latest_log_file(): void
    {
        $this->writeSnapshot('2026-04-25', [
            'date' => '2026-04-25',
            'reference_date' => '2026-04-24',
            'rankings' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.61, 'signal' => 'strong_candidate'],
            ],
            'model_version' => 'v5_ranking',
            'horizon_days' => 5,
        ]);

        $this->writeSnapshot('2026-04-26', [
            'date' => '2026-04-26',
            'reference_date' => '2026-04-25',
            'rankings' => [
                ['ticker' => 'BBRI', 'rank' => 1, 'score' => 0.63, 'signal' => 'strong_candidate'],
            ],
            'model_version' => 'v5_ranking',
            'horizon_days' => 5,
        ]);

        $snapshot = $this->makeService()->getLatestSnapshot();

        $this->assertNotNull($snapshot);
        $this->assertSame('2026-04-26', $snapshot['date']);
        $this->assertSame('BBRI', $snapshot['rankings'][0]['ticker']);
    }

    public function test_get_latest_snapshot_returns_null_when_no_log_exists(): void
    {
        $snapshot = $this->makeService()->getLatestSnapshot();

        $this->assertNull($snapshot);
    }

    public function test_get_latest_snapshot_returns_valid_snapshot_structure(): void
    {
        $this->writeSnapshot('2026-04-26', [
            'date' => '2026-04-26',
            'reference_date' => '2026-04-25',
            'rankings' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.61, 'signal' => 'strong_candidate'],
                ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.54, 'signal' => 'candidate'],
            ],
            'model_version' => 'v5_ranking',
            'horizon_days' => 5,
        ]);

        $snapshot = $this->makeService()->getLatestSnapshot();

        $this->assertNotNull($snapshot);
        $this->assertArrayHasKey('date', $snapshot);
        $this->assertArrayHasKey('rankings', $snapshot);
        $this->assertArrayHasKey('model_version', $snapshot);
        $this->assertArrayHasKey('horizon_days', $snapshot);
        $this->assertIsArray($snapshot['rankings']);
        $this->assertGreaterThan(0, count($snapshot['rankings']));
    }

    protected function makeService(): PaperTradingLogService
    {
        $liveMarketDataService = $this->createStub(LiveMarketDataService::class);
        $priceSeriesService = $this->createStub(PriceSeriesService::class);
        $featureService = $this->createStub(ResearchPredictionFeatureService::class);
        $directory = $this->tempDirectory;

        return new class($liveMarketDataService, $priceSeriesService, $featureService, $directory) extends PaperTradingLogService
        {
            public function __construct(
                LiveMarketDataService $liveMarketDataService,
                PriceSeriesService $priceSeriesService,
                ResearchPredictionFeatureService $featureService,
                protected string $directory,
            ) {
                parent::__construct($liveMarketDataService, $priceSeriesService, $featureService);
            }

            public function outputDirectory(): string
            {
                return $this->directory;
            }
        };
    }

    protected function writeSnapshot(string $date, array $payload): void
    {
        File::put(
            $this->tempDirectory."/log_{$date}.json",
            json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );
    }
}
