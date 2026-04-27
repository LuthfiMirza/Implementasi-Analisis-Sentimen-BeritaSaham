<?php

namespace App\Services\PaperTrading;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\Prediction\ResearchPredictionFeatureService;
use App\Services\Stocks\PriceSeriesService;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\File;

class PaperTradingLogService
{
    public const BUSINESS_TIMEZONE = 'Asia/Jakarta';

    public function __construct(
        protected LiveMarketDataService $liveMarketDataService,
        protected PriceSeriesService $priceSeriesService,
        protected ResearchPredictionFeatureService $featureService,
    ) {
    }

    public function outputDirectory(): string
    {
        return base_path('output/paper_trading');
    }

    public function ensureOutputDirectory(): string
    {
        $dir = $this->outputDirectory();
        File::ensureDirectoryExists($dir);

        return $dir;
    }

    public function snapshotPath(string $date): string
    {
        return $this->outputDirectory().DIRECTORY_SEPARATOR."log_{$date}.json";
    }

    public function resultsCsvPath(): string
    {
        return $this->outputDirectory().DIRECTORY_SEPARATOR.'results_log.csv';
    }

    public function latestSnapshotPayload(): ?array
    {
        return $this->getLatestSnapshot();
    }

    public function getLatestSnapshot(): ?array
    {
        $files = collect(glob($this->outputDirectory().DIRECTORY_SEPARATOR.'log_*.json') ?: [])
            ->sort()
            ->values();

        $path = $files->last();
        if (! $path || ! File::exists($path)) {
            return null;
        }

        $payload = json_decode((string) File::get($path), true);

        return $this->isValidSnapshotPayload($payload) ? $payload : null;
    }

    public function latestSnapshotVersion(): string
    {
        $files = collect(glob($this->outputDirectory().DIRECTORY_SEPARATOR.'log_*.json') ?: [])
            ->sort()
            ->values();

        $path = $files->last();
        if (! $path || ! File::exists($path)) {
            return 'no_snapshot';
        }

        $mtime = File::lastModified($path);

        return md5($path.'|'.$mtime);
    }

    public function watchlistRankingFromLatestSnapshot(array $stockCodes): array
    {
        $codes = collect($stockCodes)
            ->map(fn ($code) => strtoupper(trim((string) $code)))
            ->filter()
            ->unique()
            ->values();

        if ($codes->count() < 2) {
            return $this->unavailableRanking('Minimal dua ticker diperlukan untuk relative technical strength ranking.');
        }

        $snapshot = $this->latestSnapshotPayload();
        if (! $snapshot) {
            return $this->unavailableRanking(
                'Snapshot ranking harian belum tersedia. Jalankan paper-trading snapshot terlebih dahulu.',
                $codes->all()
            );
        }

        $rowsByTicker = collect($snapshot['rankings'])
            ->map(function (array $row): array {
                return [
                    'ticker' => strtoupper((string) ($row['ticker'] ?? '')),
                    'rank' => (int) ($row['rank'] ?? 0),
                    'score' => round((float) ($row['score'] ?? 0), 4),
                    'signal' => (string) ($row['signal'] ?? 'neutral'),
                    'price_at_snapshot' => isset($row['price_at_snapshot']) && is_numeric($row['price_at_snapshot'])
                        ? round((float) $row['price_at_snapshot'], 4)
                        : null,
                ];
            })
            ->filter(fn (array $row): bool => $row['ticker'] !== '')
            ->keyBy('ticker');

        $eligibleTickers = $codes->filter(fn (string $code): bool => $rowsByTicker->has($code))->values();
        $excludedTickers = $codes->diff($eligibleTickers)->values();

        if ($eligibleTickers->count() < 2) {
            return $this->unavailableRanking(
                'Ticker watchlist yang memiliki ranking snapshot belum cukup untuk dibandingkan.',
                $codes->all(),
                $eligibleTickers->all(),
                $excludedTickers->all(),
                (string) ($snapshot['reference_date'] ?? null),
                (string) ($snapshot['date'] ?? null),
            );
        }

        $ranked = $eligibleTickers
            ->map(fn (string $code): array => $rowsByTicker->get($code))
            ->sortBy([
                ['score', 'desc'],
                ['ticker', 'asc'],
            ])
            ->values()
            ->map(function (array $row, int $index): array {
                $row['rank'] = $index + 1;

                return $row;
            })
            ->all();

        return [
            'available' => true,
            'message' => null,
            'ranked' => $ranked,
            'model_version' => (string) ($snapshot['model_version'] ?? 'v5_ranking'),
            'horizon_days' => (int) ($snapshot['horizon_days'] ?? 5),
            'generated_at' => (string) ($snapshot['date'] ?? now()->toDateString()),
            'reference_date' => (string) ($snapshot['reference_date'] ?? ''),
            'snapshot_date' => (string) ($snapshot['date'] ?? ''),
            'requested_tickers' => $codes->all(),
            'eligible_tickers' => $eligibleTickers->all(),
            'excluded_tickers' => $excludedTickers->all(),
            'source' => 'paper_trading_snapshot',
        ];
    }

    public function activeWatchlistStocks(): Collection
    {
        return Stock::query()
            ->where('is_active', true)
            ->whereHas('watchlists')
            ->with('latestPrice')
            ->orderBy('code')
            ->get();
    }

    public function rankableWatchlistStocks(): Collection
    {
        return $this->activeWatchlistStocks()
            ->filter(fn (Stock $stock): bool => $this->featureService->seriesForStock($stock)->isNotEmpty())
            ->values();
    }

    public function resolveSnapshotPrice(Stock $stock): ?float
    {
        $quote = $this->liveMarketDataService->quote($stock);
        foreach (['last', 'close', 'open'] as $field) {
            $value = $quote[$field] ?? null;
            if ($value !== null && is_numeric($value)) {
                return round((float) $value, 4);
            }
        }

        if ($stock->latestPrice?->close !== null) {
            return round((float) $stock->latestPrice->close, 4);
        }

        $snapshot = $this->priceSeriesService->latestSnapshot($stock, '1d');

        return $snapshot?->close !== null ? round((float) $snapshot->close, 4) : null;
    }

    public function evaluationTargetForSnapshotDate(
        Stock $stock,
        CarbonInterface|string $snapshotDate,
        int $horizonDays = 5
    ): ?array {
        $basePoint = Carbon::parse($snapshotDate, self::BUSINESS_TIMEZONE)->toDateString();
        $series = $this->priceSeriesService->getSeries($stock, '1d', 10000);

        if ($series->isEmpty()) {
            return null;
        }

        $rows = $series->values();
        $baseIndex = $rows->search(function (StockPrice $row) use ($basePoint): bool {
            return Carbon::parse($row->price_date)->toDateString() === $basePoint;
        });

        if ($baseIndex === false) {
            $baseIndex = $rows->search(function (StockPrice $row) use ($basePoint): bool {
                return Carbon::parse($row->price_date)->toDateString() >= $basePoint;
            });
        }

        if ($baseIndex === false) {
            return null;
        }

        $targetIndex = $baseIndex + $horizonDays;
        $targetRow = $rows->get($targetIndex);

        if (! $targetRow || $targetRow->close === null) {
            return null;
        }

        return [
            'price' => round((float) $targetRow->close, 4),
            'price_date' => Carbon::parse($targetRow->price_date)->toDateString(),
        ];
    }

    public function businessToday(): Carbon
    {
        return Carbon::now(self::BUSINESS_TIMEZONE);
    }

    protected function unavailableRanking(
        string $message,
        array $requestedTickers = [],
        array $eligibleTickers = [],
        array $excludedTickers = [],
        ?string $referenceDate = null,
        ?string $snapshotDate = null,
    ): array {
        return [
            'available' => false,
            'message' => $message,
            'ranked' => [],
            'model_version' => 'v5_ranking',
            'horizon_days' => 5,
            'generated_at' => now()->toDateString(),
            'reference_date' => $referenceDate,
            'snapshot_date' => $snapshotDate,
            'requested_tickers' => $requestedTickers,
            'eligible_tickers' => $eligibleTickers,
            'excluded_tickers' => $excludedTickers,
            'source' => 'paper_trading_snapshot',
        ];
    }

    protected function isValidSnapshotPayload(mixed $payload): bool
    {
        return is_array($payload)
            && isset($payload['date'], $payload['rankings'], $payload['model_version'], $payload['horizon_days'])
            && is_array($payload['rankings']);
    }
}
