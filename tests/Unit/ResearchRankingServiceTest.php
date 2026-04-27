<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\Prediction\ResearchPredictionFeatureService;
use App\Services\Prediction\ResearchRankingService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ResearchRankingServiceTest extends TestCase
{
    use RefreshDatabase;

    protected string $tempRoot;

    protected string $stockDataDir;

    protected string $ihsgCsvPath;

    protected function setUp(): void
    {
        parent::setUp();

        $this->tempRoot = sys_get_temp_dir().'/sentimena-ranking-tests-'.bin2hex(random_bytes(5));
        $this->stockDataDir = $this->tempRoot.'/stocks';
        $this->ihsgCsvPath = $this->tempRoot.'/IHSG.csv';

        File::ensureDirectoryExists($this->stockDataDir);
        $this->writePriceCsv('IHSG', $this->ihsgCsvPath, 260, 7000.0);
    }

    protected function tearDown(): void
    {
        File::deleteDirectory($this->tempRoot);

        parent::tearDown();
    }

    public function test_get_ranking_returns_ranked_payload_from_fastapi(): void
    {
        Stock::factory()->create(['code' => 'BBCA']);
        Stock::factory()->create(['code' => 'BBRI']);

        $this->writeStockSeries('BBCA', 1200.0);
        $this->writeStockSeries('BBRI', 1100.0);

        $endpoint = 'http://ranking.test/rank-stocks';

        Http::fake([
            $endpoint => Http::response([
                'ranked' => [
                    ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.6123, 'signal' => 'strong_candidate'],
                    ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.5341, 'signal' => 'candidate'],
                ],
                'model_version' => 'v5_ranking',
                'horizon_days' => 5,
                'generated_at' => '2026-04-26',
            ], 200),
        ]);

        $result = $this->makeService($endpoint)->getRanking(['BBCA', 'BBRI']);

        $this->assertTrue($result['available']);
        $this->assertCount(2, $result['ranked']);
        $this->assertSame(['BBCA', 'BBRI'], array_column($result['ranked'], 'ticker'));
        $this->assertSame(['ticker', 'rank', 'score', 'signal'], array_keys($result['ranked'][0]));
        $this->assertSame(['BBCA', 'BBRI'], $result['eligible_tickers']);
        $this->assertSame([], $result['excluded_tickers']);

        Http::assertSent(function (Request $request) use ($endpoint): bool {
            $payload = $request->data();

            return $request->url() === $endpoint
                && count($payload['stocks'] ?? []) === 2;
        });
    }

    public function test_get_ranking_returns_unavailable_payload_when_fastapi_fails(): void
    {
        Stock::factory()->create(['code' => 'BBCA']);
        Stock::factory()->create(['code' => 'BBRI']);

        $this->writeStockSeries('BBCA', 1200.0);
        $this->writeStockSeries('BBRI', 1100.0);

        Http::fake(fn (): never => throw new \RuntimeException('FastAPI timeout'));

        $result = $this->makeService('http://ranking.test/rank-stocks')->getRanking(['BBCA', 'BBRI']);

        $this->assertFalse($result['available']);
        $this->assertSame([], $result['ranked']);
        $this->assertNotEmpty($result['message']);
    }

    public function test_get_ranking_excludes_tickers_without_feature_coverage(): void
    {
        Stock::factory()->create(['code' => 'BBCA']);
        Stock::factory()->create(['code' => 'BBRI']);
        Stock::factory()->create(['code' => 'GOTO']);

        $this->writeStockSeries('BBCA', 1200.0);
        $this->writeStockSeries('BBRI', 1100.0);

        $endpoint = 'http://ranking.test/rank-stocks';

        Http::fake([
            $endpoint => Http::response([
                'ranked' => [
                    ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.6123, 'signal' => 'strong_candidate'],
                    ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.5341, 'signal' => 'candidate'],
                ],
                'model_version' => 'v5_ranking',
                'horizon_days' => 5,
                'generated_at' => '2026-04-26',
            ], 200),
        ]);

        $result = $this->makeService($endpoint)->getRanking(['BBCA', 'BBRI', 'GOTO']);

        $this->assertTrue($result['available']);
        $this->assertSame(['BBCA', 'BBRI'], $result['eligible_tickers']);
        $this->assertSame(['GOTO'], $result['excluded_tickers']);
        $this->assertSame(['BBCA', 'BBRI'], array_column($result['ranked'], 'ticker'));
    }

    protected function makeService(string $endpoint): ResearchRankingService
    {
        return new ResearchRankingService(
            new ResearchPredictionFeatureService($this->stockDataDir, $this->ihsgCsvPath),
            $endpoint,
            3,
        );
    }

    protected function writeStockSeries(string $code, float $basePrice): void
    {
        $this->writePriceCsv($code, $this->stockDataDir.'/'.$code.'.csv', 120, $basePrice);
    }

    protected function writePriceCsv(string $code, string $path, int $days, float $basePrice): void
    {
        $rows = ['date,open,high,low,close,adj_close,volume'];
        $startDate = Carbon::parse('2024-01-01');

        for ($i = 0; $i < $days; $i++) {
            $close = $basePrice + ($i * 2.5);
            $open = $close - 1.2;
            $high = $close + 3.4;
            $low = $close - 3.8;
            $adjClose = $close;
            $volume = 1_000_000 + ($i * 1000);

            $rows[] = implode(',', [
                $startDate->copy()->addDays($i)->toDateString(),
                number_format($open, 4, '.', ''),
                number_format($high, 4, '.', ''),
                number_format($low, 4, '.', ''),
                number_format($close, 4, '.', ''),
                number_format($adjClose, 4, '.', ''),
                $volume,
            ]);
        }

        File::put($path, implode(PHP_EOL, $rows).PHP_EOL);
    }
}
