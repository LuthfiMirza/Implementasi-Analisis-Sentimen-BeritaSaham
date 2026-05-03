<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Services\PaperTrading\PaperTradingLogService;
use App\Services\Prediction\ResearchRankingService;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class PaperTradingCommandTest extends TestCase
{
    public function test_paper_trading_record_snapshot_command_runs_without_exception(): void
    {
        $this->bindPaperTradingFakes();

        // Snapshot recording is the scheduled source for watchlist ranking audit logs.
        $this->artisan('paper-trading:record-snapshot --date=2026-04-30')->assertExitCode(0);
    }

    public function test_paper_trading_evaluate_result_returns_valid_csv_row_for_known_snapshot_date(): void
    {
        $service = $this->bindPaperTradingFakes();
        File::ensureDirectoryExists($service->outputDirectory());
        File::put($service->snapshotPath('2026-04-30'), json_encode([
            'date' => '2026-04-30',
            'reference_date' => '2026-04-29',
            'horizon_days' => 5,
            'model_version' => 'test-v1',
            'rankings' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.9, 'signal' => 'strong_candidate', 'price_at_snapshot' => 1000],
                ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.5, 'signal' => 'neutral', 'price_at_snapshot' => 900],
            ],
        ]));

        $this->artisan('paper-trading:evaluate-result --date=2026-04-30')->assertExitCode(0);

        // CSV result row is the durable evaluation artifact for a known snapshot.
        $csv = File::get($service->resultsCsvPath());
        $this->assertStringContainsString('snapshot_date,eval_date,spearman,long_short_spread,top3_precision,top1_hit,notes', $csv);
        $this->assertStringContainsString('2026-04-30', $csv);
    }

    private function bindPaperTradingFakes(): PaperTradingLogService
    {
        $bbca = $this->seedStock('BBCA');
        $bbri = $this->seedStock('BBRI');

        $paper = new class($bbca, $bbri) extends PaperTradingLogService {
            public function __construct(private Stock $bbca, private Stock $bbri) {}
            public function outputDirectory(): string
            {
                return base_path('storage/framework/testing/output/paper_trading_commands');
            }
            public function activeWatchlistStocks(): Collection
            {
                return collect([$this->bbca, $this->bbri]);
            }
            public function rankableWatchlistStocks(): Collection
            {
                return collect([$this->bbca, $this->bbri]);
            }
            public function resolveSnapshotPrice(Stock $stock): ?float
            {
                return $stock->code === 'BBCA' ? 1000.0 : 900.0;
            }
            public function evaluationTargetForSnapshotDate(Stock $stock, $snapshotDate, int $horizonDays = 5): ?array
            {
                return ['price' => $stock->code === 'BBCA' ? 1100.0 : 880.0, 'price_date' => '2026-05-07'];
            }
        };

        $ranking = new class extends ResearchRankingService {
            public function __construct() {}
            public function getRanking(array $stockCodes): array
            {
                return [
                    'available' => true,
                    'reference_date' => '2026-04-29',
                    'model_version' => 'test-v1',
                    'horizon_days' => 5,
                    'ranked' => [
                        ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.9, 'signal' => 'strong_candidate'],
                        ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.5, 'signal' => 'neutral'],
                    ],
                ];
            }
        };

        $this->app->instance(PaperTradingLogService::class, $paper);
        $this->app->instance(ResearchRankingService::class, $ranking);

        return $paper;
    }
}
