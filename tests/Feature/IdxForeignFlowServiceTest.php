<?php

namespace Tests\Feature;

use App\Services\MarketData\IdxForeignFlowService;
use Tests\TestCase;

class IdxForeignFlowServiceTest extends TestCase
{
    public function test_parses_foreign_accumulation_payload_accurately(): void
    {
        $svc = app(IdxForeignFlowService::class);
        $parsed = $svc->parseForeignPayload([
            'schema' => 'idx.foreign.v1',
            'data' => [
                'symbol' => 'ENRG',
                'days' => [
                    ['date' => '2026-11-18', 'foreign_net_value_at_close' => 3_770_000_000],
                    ['date' => '2026-11-19', 'foreign_net_value_at_close' => 7_880_000_000],
                    ['date' => '2026-11-20', 'foreign_net_value_at_close' => -443_000_000],
                    ['date' => '2026-11-23', 'foreign_net_value_at_close' => 12_210_000_000],
                    ['date' => '2026-11-24', 'foreign_net_value_at_close' => 480_700_000],
                ],
            ],
        ]);

        $this->assertNotNull($parsed);
        $this->assertSame('FOREIGN_ACCUM', $parsed['status']);
        $this->assertSame(4, $parsed['buy_days']);
        $this->assertSame(1, $parsed['sell_days']);
        $this->assertSame(2, $parsed['streak_days']);
        $this->assertSame('+Rp23,9M', $parsed['net_5d_formatted']);
        $this->assertSame('+Rp481Jt', $parsed['net_1d_formatted']);
    }

    public function test_computes_negative_streak_and_participation_ratio(): void
    {
        $svc = app(IdxForeignFlowService::class);
        $parsed = $svc->parseForeignPayload([
            'data' => [
                'symbol' => 'BRPT',
                'days' => [
                    ['date' => '2026-11-20', 'value' => 100_000_000_000, 'foreign_net_value_at_close' => 5_000_000_000],
                    ['date' => '2026-11-23', 'value' => 100_000_000_000, 'foreign_net_value_at_close' => -15_000_000_000],
                    ['date' => '2026-11-24', 'value' => 100_000_000_000, 'foreign_net_value_at_close' => -20_000_000_000],
                    ['date' => '2026-11-25', 'value' => 100_000_000_000, 'foreign_net_value_at_close' => -30_000_000_000],
                ],
            ],
        ]);

        $this->assertNotNull($parsed);
        $this->assertSame(-3, $parsed['streak_days']);
        $this->assertSame(17.5, $parsed['participation_pct']);
    }

    public function test_parses_foreign_reversal_1d_and_distribution_payloads(): void
    {
        $svc = app(IdxForeignFlowService::class);

        // ISAT: 5D negative overall, but massive +18B single-day reversal buy today
        $isat = $svc->parseForeignPayload([
            'data' => [
                'symbol' => 'ISAT',
                'days' => [
                    ['date' => '2026-11-20', 'foreign_net_value_at_close' => -20_000_000_000],
                    ['date' => '2026-11-23', 'foreign_net_value_at_close' => -3_000_000_000],
                    ['date' => '2026-11-24', 'foreign_net_value_at_close' => 18_010_000_000],
                ],
            ],
        ]);
        $this->assertSame('FOREIGN_REVERSAL', $isat['status']);

        // BRPT: 4/5 sell days & heavy -65.5B outflow
        $brpt = $svc->parseForeignPayload([
            'data' => [
                'symbol' => 'BRPT',
                'days' => [
                    ['date' => '2026-11-18', 'foreign_net_value_at_close' => -15_000_000_000],
                    ['date' => '2026-11-19', 'foreign_net_value_at_close' => -18_000_000_000],
                    ['date' => '2026-11-20', 'foreign_net_value_at_close' => -10_400_000_000],
                    ['date' => '2026-11-23', 'foreign_net_value_at_close' => 14_140_000_000],
                    ['date' => '2026-11-24', 'foreign_net_value_at_close' => -36_240_000_000],
                ],
            ],
        ]);
        $this->assertSame('FOREIGN_DIST', $brpt['status']);
        $this->assertSame(4, $brpt['sell_days']);
        $this->assertSame('-Rp65,5M', $brpt['net_5d_formatted']);
    }

    public function test_returns_null_gracefully_on_empty_or_invalid_payload(): void
    {
        $svc = app(IdxForeignFlowService::class);
        $this->assertNull($svc->parseForeignPayload([]));
        $this->assertNull($svc->summarize('ENRG', 5)); // skipped safely in unit test env
    }
}

