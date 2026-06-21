<?php

namespace App\Services\Stocks;

use App\Models\Stock;
use App\Models\StockPrice;
use Illuminate\Support\Collection;

class PriceSeriesService
{
    public function getSeries(Stock $stock, string $interval = '1d', int $limit = 90): Collection
    {
        return $this->normalizedSeries($stock, $interval)
            ->take(-1 * $limit)
            ->values();
    }

    public function latestSnapshot(Stock $stock, string $interval = '1d')
    {
        return $this->normalizedSeries($stock, $interval)->last();
    }

    public function latestWithChange(Stock $stock, string $interval = '1d'): array
    {
        $latest = $this->normalizedSeries($stock, $interval)->take(-2)->values();

        $last = $latest->last();
        $previous = $latest->count() > 1 ? $latest->first() : null;

        $changePct = null;
        if ($last && $previous && $previous->close) {
            $changePct = (($last->close - $previous->close) / $previous->close) * 100;
        }

        return [
            'latest' => $last,
            'previous' => $previous,
            'change_pct' => $changePct ? round($changePct, 2) : null,
        ];
    }

    protected function normalizedSeries(Stock $stock, string $interval = '1d'): Collection
    {
        $rows = StockPrice::where('stock_id', $stock->id)
            ->when($interval, fn ($q) => $q->where('interval_type', $interval))
            ->get()
            ->sortBy('price_date')
            ->values();

        return StockPrice::canonicalize($rows);
    }
}
