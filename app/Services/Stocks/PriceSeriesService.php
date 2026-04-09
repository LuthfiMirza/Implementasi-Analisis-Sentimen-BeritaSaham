<?php

namespace App\Services\Stocks;

use App\Models\Stock;
use App\Models\StockPrice;
use Illuminate\Support\Collection;

class PriceSeriesService
{
    public function getSeries(Stock $stock, string $interval = '1d', int $limit = 90): Collection
    {
        return StockPrice::where('stock_id', $stock->id)
            ->when($interval, fn ($q) => $q->where('interval_type', $interval))
            ->orderByDesc('price_date')
            ->limit($limit)
            ->get()
            ->sortBy('price_date')
            ->values();
    }

    public function latestWithChange(Stock $stock, string $interval = '1d'): array
    {
        $latest = StockPrice::where('stock_id', $stock->id)
            ->when($interval, fn ($q) => $q->where('interval_type', $interval))
            ->latest('price_date')
            ->take(2)
            ->get();

        $last = $latest->first();
        $previous = $latest->skip(1)->first();

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
}
