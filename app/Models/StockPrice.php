<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;

class StockPrice extends Model
{
    /** @use HasFactory<\Database\Factories\StockPriceFactory> */
    use HasFactory;

    protected $fillable = [
        'stock_id',
        'price_date',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'source',
        'interval_type',
    ];

    protected $casts = [
        'price_date' => 'datetime',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class);
    }

    /**
     * Collapse duplicated daily rows into one canonical row per trade date.
     *
     * @param  Collection<int, self>  $rows
     * @return Collection<int, self>
     */
    public static function canonicalize(Collection $rows): Collection
    {
        $candidateRows = $rows;
        if ($rows->contains(fn (self $row): bool => ($row->source ?? '') !== 'seed')) {
            $candidateRows = $rows
                ->filter(fn (self $row): bool => ($row->source ?? '') !== 'seed')
                ->values();
        }

        return $candidateRows
            ->groupBy(fn (self $row): string => Carbon::parse($row->price_date)->toDateString())
            ->map(fn (Collection $group): ?self => $group
                ->sort(fn (self $left, self $right): int => self::compareCanonicalRows($left, $right))
                ->first())
            ->filter()
            ->sortBy(fn (self $row): int => Carbon::parse($row->price_date)->getTimestamp())
            ->values();
    }

    public static function sourcePriority(?string $source): int
    {
        return match ($source) {
            'yahoo_history_incremental', 'yahoo_daily_rebuild_raw' => 0,
            null => 1,
            'command' => 2,
            'seed' => 3,
            default => 2,
        };
    }

    protected static function compareCanonicalRows(self $left, self $right): int
    {
        $leftRank = self::sourcePriority($left->source);
        $rightRank = self::sourcePriority($right->source);

        if ($leftRank !== $rightRank) {
            return $leftRank <=> $rightRank;
        }

        $leftVolume = (int) ($left->volume ?? 0);
        $rightVolume = (int) ($right->volume ?? 0);
        if ($leftVolume !== $rightVolume) {
            return $rightVolume <=> $leftVolume;
        }

        return ((int) $right->id) <=> ((int) $left->id);
    }
}
