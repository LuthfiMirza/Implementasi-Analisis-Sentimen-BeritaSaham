<?php

namespace App\Services\Stocks;

use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
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

        return $this->collapseDailyDuplicates($rows);
    }

    protected function collapseDailyDuplicates(Collection $rows): Collection
    {
        $normalizedRows = $rows;
        if ($rows->contains(fn (StockPrice $row) => ($row->source ?? '') !== 'seed')) {
            $normalizedRows = $rows
                ->filter(fn (StockPrice $row) => ($row->source ?? '') !== 'seed')
                ->values();
        }

        return $normalizedRows
            ->groupBy(fn (StockPrice $row) => Carbon::parse($row->price_date)->toDateString())
            ->map(function (Collection $group) {
                return $group
                    ->sort(function (StockPrice $left, StockPrice $right): int {
                        $leftRank = $this->sourcePriority($left);
                        $rightRank = $this->sourcePriority($right);

                        if ($leftRank !== $rightRank) {
                            return $leftRank <=> $rightRank;
                        }

                        return Carbon::parse($right->price_date)->getTimestamp()
                            <=> Carbon::parse($left->price_date)->getTimestamp();
                    })
                    ->first();
            })
            ->sortBy(fn (StockPrice $row) => Carbon::parse($row->price_date)->getTimestamp())
            ->values();
    }

    protected function sourcePriority(StockPrice $row): int
    {
        if (($row->source ?? '') === 'seed') {
            return 2;
        }

        if (($row->source ?? null) === null) {
            return 0;
        }

        return 1;
    }
}
