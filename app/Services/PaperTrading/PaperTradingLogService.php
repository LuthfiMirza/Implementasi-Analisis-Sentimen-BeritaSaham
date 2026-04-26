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
}
