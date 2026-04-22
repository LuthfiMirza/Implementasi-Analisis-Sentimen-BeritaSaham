<?php

namespace Tests\Unit;

use App\Services\Stocks\DailyPriceSeriesValidator;
use Tests\TestCase;

class DailyPriceSeriesValidatorTest extends TestCase
{
    public function test_validator_accepts_clean_daily_series(): void
    {
        $validator = app(DailyPriceSeriesValidator::class);

        $rows = [];
        $date = new \DateTimeImmutable('2025-01-02');
        for ($index = 0; $index < 260; $index++) {
            while ((int) $date->format('N') >= 6) {
                $date = $date->modify('+1 day');
            }

            $rows[] = [
                'date' => $date->format('Y-m-d'),
                'open' => 100 + $index,
                'high' => 105 + $index,
                'low' => 95 + $index,
                'close' => 102 + $index,
                'volume' => 100000 + $index,
            ];

            $date = $date->modify('+1 day');
        }

        $result = $validator->validate($rows);

        $this->assertTrue($result['valid']);
        $this->assertSame([], $result['errors']);
    }

    public function test_validator_rejects_weekend_rows_and_large_non_daily_gaps(): void
    {
        $validator = app(DailyPriceSeriesValidator::class);

        $rows = [
            ['date' => '2024-01-31', 'open' => 100, 'high' => 102, 'low' => 99, 'close' => 101, 'volume' => 1000],
            ['date' => '2024-02-29', 'open' => 101, 'high' => 103, 'low' => 100, 'close' => 102, 'volume' => 1000],
            ['date' => '2024-03-31', 'open' => 102, 'high' => 104, 'low' => 101, 'close' => 103, 'volume' => 1000],
            ['date' => '2024-04-30', 'open' => 103, 'high' => 105, 'low' => 102, 'close' => 104, 'volume' => 1000],
            ['date' => '2025-01-03', 'open' => 200, 'high' => 202, 'low' => 199, 'close' => 201, 'volume' => 1000],
        ];

        $result = $validator->validate($rows);

        $this->assertFalse($result['valid']);
        $this->assertContains('weekend_rows_present', $result['errors']);
        $this->assertContains('non_daily_gap_detected', $result['errors']);
    }
}
