<?php

namespace Tests\Feature;

use App\Models\IdxDailySummary;
use App\Models\KseiOwnership;
use App\Services\MarketData\IdxMarketSummaryService;
use Illuminate\Support\Carbon;
use Tests\TestCase;

class IdxMarketSummaryServiceTest extends TestCase
{
    private function row(string $date, string $code, array $overrides = []): void
    {
        $close = $overrides['close'] ?? 1000.0;
        $previous = $overrides['previous'] ?? $close;
        $change = $close - $previous;

        IdxDailySummary::create(array_merge([
            'trade_date' => $date,
            'stock_code' => $code,
            'stock_name' => "{$code} Tbk",
            'previous' => $previous,
            'open' => $overrides['open'] ?? $close,
            'high' => $close,
            'low' => $close,
            'close' => $close,
            'change' => $change,
            'pct_change' => $previous > 0 ? round($change / $previous * 100, 4) : 0,
            'volume' => $overrides['volume'] ?? 1_000_000,
            'value' => $overrides['value'] ?? 5_000_000_000,
            'frequency' => 100,
            'foreign_buy' => $overrides['foreign_buy'] ?? 0,
            'foreign_sell' => $overrides['foreign_sell'] ?? 0,
            'foreign_net' => ($overrides['foreign_buy'] ?? 0) - ($overrides['foreign_sell'] ?? 0),
            'foreign_net_value' => (($overrides['foreign_buy'] ?? 0) - ($overrides['foreign_sell'] ?? 0)) * $close,
            'source' => 'test',
        ], array_intersect_key($overrides, array_flip(['listed_shares', 'remarks']))));
    }

    private function seedHistory(string $code, int $priorDays, array $latest): string
    {
        $latestDate = Carbon::parse('2026-08-28');
        for ($i = $priorDays; $i >= 1; $i--) {
            $this->row($latestDate->copy()->subDays($i + 2)->toDateString(), $code, ['volume' => 1_000_000]);
        }
        $this->row($latestDate->toDateString(), $code, $latest);

        return $latestDate->toDateString();
    }

    public function test_volume_alert_fires_when_today_exceeds_moving_average_ratio(): void
    {
        // Prior days sit at 1,000,000 volume for every name (seedHistory hardcodes that).
        $date = $this->seedHistory('SPIKE', 12, ['volume' => 6_000_000, 'value' => 6_000_000_000]); // 6x -> fires
        $this->seedHistory('MILD', 12, ['volume' => 4_000_000, 'value' => 6_000_000_000]);          // 4x -> below 5x bar
        $this->seedHistory('CALM', 12, ['volume' => 1_050_000, 'value' => 6_000_000_000]);          // ~flat

        $alerts = collect(app(IdxMarketSummaryService::class)->volumeAlerts($date));

        $this->assertTrue($alerts->contains('stock_code', 'SPIKE'));
        $this->assertFalse($alerts->contains('stock_code', 'MILD'));
        $this->assertFalse($alerts->contains('stock_code', 'CALM'));
        $this->assertEqualsWithDelta(6.0, $alerts->firstWhere('stock_code', 'SPIKE')['volume_ratio'], 0.1);
    }

    public function test_volume_alert_skips_illiquid_names_below_min_value(): void
    {
        $date = $this->seedHistory('THIN', 12, ['volume' => 9_000_000, 'value' => 100_000_000]);

        $alerts = collect(app(IdxMarketSummaryService::class)->volumeAlerts($date));

        $this->assertFalse($alerts->contains('stock_code', 'THIN'));
    }

    public function test_gap_alert_flags_large_opening_gap(): void
    {
        // GAPPER: +8% opening gap, liquid -> fires on the gap branch.
        $this->row('2026-08-28', 'GAPPER', ['previous' => 1000, 'open' => 1080, 'close' => 1050, 'value' => 20_000_000_000]);
        // STEADY: 0.5% gap, 1% move -> below both thresholds.
        $this->row('2026-08-28', 'STEADY', ['previous' => 1000, 'open' => 1005, 'close' => 1010, 'value' => 20_000_000_000]);
        // NOOPEN: no opening auction (open 0) but closed -14% -> fires on the move branch, gap_pct null.
        $this->row('2026-08-28', 'NOOPEN', ['previous' => 1000, 'open' => 0, 'close' => 860, 'value' => 20_000_000_000]);
        // THIN: +9% gap but illiquid -> filtered out by min turnover.
        $this->row('2026-08-28', 'THIN', ['previous' => 1000, 'open' => 1090, 'close' => 1090, 'value' => 500_000_000]);

        $alerts = collect(app(IdxMarketSummaryService::class)->gapAlerts('2026-08-28'));

        $this->assertTrue($alerts->contains('stock_code', 'GAPPER'));
        $this->assertFalse($alerts->contains('stock_code', 'STEADY'));
        $this->assertFalse($alerts->contains('stock_code', 'THIN'));
        $this->assertEqualsWithDelta(8.0, $alerts->firstWhere('stock_code', 'GAPPER')['gap_pct'], 0.01);

        $noopen = $alerts->firstWhere('stock_code', 'NOOPEN');
        $this->assertNotNull($noopen);
        $this->assertNull($noopen['gap_pct']);
    }

    public function test_foreign_flow_alert_ranks_by_absolute_net_value_and_sets_direction(): void
    {
        // Filter is absolute rupiah only (>= Rp 30 B), ranked by |net| descending.
        // OUTFLOW: net -50,000,000 sh * 1000 = -Rp 50B -> largest, sorts first.
        // INFLOW:  net +35,000,000 sh * 1000 = +Rp 35B -> clears the floor.
        // THIN_HI_RATIO: net +5,000,000 sh * 1000 = +Rp 5B on Rp 8B turnover (62% ratio) but
        //                only Rp 5B absolute -> does NOT qualify (ratio is not a condition).
        // NEUTRAL: net 0 -> never qualifies.
        $this->row('2026-08-28', 'OUTFLOW', ['foreign_buy' => 0, 'foreign_sell' => 50_000_000, 'value' => 300_000_000_000]);
        $this->row('2026-08-28', 'INFLOW', ['foreign_buy' => 40_000_000, 'foreign_sell' => 5_000_000, 'value' => 200_000_000_000]);
        $this->row('2026-08-28', 'THIN_HI_RATIO', ['foreign_buy' => 5_000_000, 'foreign_sell' => 0, 'value' => 8_000_000_000]);
        $this->row('2026-08-28', 'NEUTRAL', ['foreign_buy' => 10_000, 'foreign_sell' => 10_000, 'value' => 50_000_000_000]);

        $alerts = collect(app(IdxMarketSummaryService::class)->foreignFlowAlerts('2026-08-28'));

        $this->assertSame('OUTFLOW', $alerts->first()['stock_code']);
        $this->assertSame('outflow', $alerts->first()['direction']);
        $this->assertSame('inflow', $alerts->firstWhere('stock_code', 'INFLOW')['direction']);
        $this->assertFalse($alerts->contains('stock_code', 'THIN_HI_RATIO'));
        $this->assertFalse($alerts->contains('stock_code', 'NEUTRAL'));
    }

    public function test_ownership_alert_flags_month_over_month_foreign_shift_only(): void
    {
        $mk = function (string $code, float $delta, string $source = 'ksei_manual') {
            KseiOwnership::create([
                'snapshot_date' => '2026-07-31', 'stock_code' => $code, 'stock_name' => "{$code} Tbk",
                'total_shares' => 1_000_000, 'local_shares' => 700_000, 'foreign_shares' => 300_000,
                'local_pct' => 70, 'foreign_pct' => 30, 'foreign_pct_delta' => $delta, 'source' => $source,
            ]);
        };
        $mk('BIGUP', 2.5, 'ksei_sample');
        $mk('BIGDN', -1.4);
        $mk('TINY', 0.3);            // below 1.0pp threshold
        KseiOwnership::create([      // no delta yet (first snapshot) -> excluded
            'snapshot_date' => '2026-07-31', 'stock_code' => 'NEW', 'total_shares' => 1, 'local_shares' => 1,
            'foreign_shares' => 0, 'local_pct' => 100, 'foreign_pct' => 0, 'foreign_pct_delta' => null, 'source' => 'ksei_manual',
        ]);

        $alerts = collect(app(IdxMarketSummaryService::class)->ownershipAlerts());

        $this->assertEqualsCanonicalizing(['BIGUP', 'BIGDN'], $alerts->pluck('stock_code')->all());
        $this->assertSame('accumulation', $alerts->firstWhere('stock_code', 'BIGUP')['direction']);
        $this->assertSame('distribution', $alerts->firstWhere('stock_code', 'BIGDN')['direction']);
        $this->assertSame('ksei_sample', $alerts->firstWhere('stock_code', 'BIGUP')['source']);
    }

    public function test_foreign_flow_history_reports_per_day_rows_and_consistency_summary(): void
    {
        // 6 trading days: sell, sell, buy, buy, buy, buy -> latest streak = 4 buy days.
        $daily = [
            ['2026-08-24', -3_000_000],
            ['2026-08-25', -1_000_000],
            ['2026-08-26', 2_000_000],
            ['2026-08-27', 5_000_000],
            ['2026-08-28', 4_000_000],
            ['2026-08-31', 8_000_000],
        ];
        foreach ($daily as [$d, $netShares]) {
            $this->row($d, 'FGN', [
                'close' => 1000,
                'foreign_buy' => max(0, $netShares),
                'foreign_sell' => max(0, -$netShares),
                'value' => 50_000_000_000,
            ]);
        }

        $hist = app(IdxMarketSummaryService::class)->foreignFlowHistory('fgn', 20);

        $this->assertSame('FGN', $hist['stock_code']);
        $this->assertCount(6, $hist['days']);
        $this->assertSame('2026-08-24', $hist['days'][0]['date']);       // oldest first
        $this->assertSame('2026-08-31', $hist['days'][5]['date']);       // newest last
        $this->assertSame(4, $hist['summary']['buy_days']);
        $this->assertSame(2, $hist['summary']['sell_days']);
        $this->assertSame(4, $hist['summary']['streak']);
        $this->assertSame('buy', $hist['summary']['streak_dir']);
    }

    public function test_foreign_flow_history_is_empty_for_unknown_code(): void
    {
        $hist = app(IdxMarketSummaryService::class)->foreignFlowHistory('NOPE');

        $this->assertSame([], $hist['days']);
        $this->assertNull($hist['summary']);
    }

    public function test_summary_payload_is_cached_per_trade_date(): void
    {
        $this->seedHistory('SPIKE', 12, ['volume' => 6_000_000]);

        $service = app(IdxMarketSummaryService::class);
        $first = $service->summary();

        // Mutating the table should not change the cached payload until fresh=true.
        IdxDailySummary::query()->update(['volume' => 1]);

        $this->assertEquals($first, $service->summary());
        $this->assertNotEquals($first['counts'], $service->summary(true)['counts']);
    }
}
