<?php

namespace App\Services\Stocks;

use Carbon\Carbon;
use Illuminate\Support\Collection;

class DailyPriceSeriesValidator
{
    private const MAX_ALLOWED_GAP_DAYS = 14;

    private const MIN_INTERIOR_YEAR_ROWS = 120;

    /**
     * @param  iterable<int, array<string, mixed>>  $rows
     * @return array{
     *     valid: bool,
     *     errors: list<string>,
     *     metrics: array<string, mixed>
     * }
     */
    public function validate(iterable $rows): array
    {
        $normalized = collect($rows)
            ->map(function (array $row): array {
                return [
                    'date' => Carbon::parse((string) ($row['date'] ?? ''))->toDateString(),
                    'open' => isset($row['open']) ? (float) $row['open'] : null,
                    'high' => isset($row['high']) ? (float) $row['high'] : null,
                    'low' => isset($row['low']) ? (float) $row['low'] : null,
                    'close' => isset($row['close']) ? (float) $row['close'] : null,
                    'volume' => isset($row['volume']) ? (int) $row['volume'] : null,
                ];
            })
            ->values();

        $errors = [];
        $dates = $normalized->pluck('date')->values();

        if ($normalized->isEmpty()) {
            return [
                'valid' => false,
                'errors' => ['price_series_empty'],
                'metrics' => [],
            ];
        }

        $parsedDates = $dates->map(fn (string $date): Carbon => Carbon::parse($date))->values();
        $weekendRows = $parsedDates
            ->filter(fn (Carbon $date): bool => $date->isWeekend())
            ->count();

        if ($weekendRows > 0) {
            $errors[] = 'weekend_rows_present';
        }

        if ($dates->count() !== $dates->unique()->count()) {
            $errors[] = 'duplicate_dates_present';
        }

        $isMonotonicAscending = true;
        $maxGapDays = 0;
        for ($index = 1; $index < $parsedDates->count(); $index++) {
            $previous = $parsedDates[$index - 1];
            $current = $parsedDates[$index];
            $gapDays = $previous->diffInDays($current, false);

            if ($gapDays <= 0) {
                $isMonotonicAscending = false;
            }

            $maxGapDays = max($maxGapDays, max(0, $gapDays));
        }

        if (! $isMonotonicAscending) {
            $errors[] = 'dates_not_strictly_ascending';
        }

        if ($maxGapDays > self::MAX_ALLOWED_GAP_DAYS) {
            $errors[] = 'non_daily_gap_detected';
        }

        $rowsPerYear = $parsedDates
            ->groupBy(fn (Carbon $date): int => $date->year)
            ->map(fn (Collection $group): int => $group->count())
            ->sortKeys();

        $firstYear = (int) $parsedDates->first()->year;
        $lastYear = (int) $parsedDates->last()->year;
        $interiorYears = $rowsPerYear
            ->filter(fn (int $count, int $year): bool => $year > $firstYear && $year < $lastYear);
        $suspiciousInteriorYears = $interiorYears
            ->filter(fn (int $count): bool => $count < self::MIN_INTERIOR_YEAR_ROWS);

        if ($suspiciousInteriorYears->isNotEmpty()) {
            $errors[] = 'mixed_frequency_contamination_detected';
        }

        return [
            'valid' => $errors === [],
            'errors' => $errors,
            'metrics' => [
                'row_count' => $normalized->count(),
                'weekend_rows' => $weekendRows,
                'max_gap_days' => $maxGapDays,
                'rows_per_year' => $rowsPerYear->all(),
                'suspicious_interior_years' => $suspiciousInteriorYears->all(),
            ],
        ];
    }
}
