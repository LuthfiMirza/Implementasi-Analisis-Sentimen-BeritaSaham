<?php

namespace Tests\Feature;

use App\Models\IdxDailySummary;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class FetchIdxDailySummaryCommandTest extends TestCase
{
    private function wrapperJson(string $isoDate, array $rows): string
    {
        return json_encode(['date' => $isoDate, 'count' => count($rows), 'rows' => $rows]);
    }

    private function idxRow(string $code, array $o = []): array
    {
        return array_merge([
            'StockCode' => $code,
            'StockName' => "{$code} Tbk",
            'Remarks' => '--',
            'Previous' => 1000.0,
            'OpenPrice' => 1010.0,
            'High' => 1050.0,
            'Low' => 990.0,
            'Close' => 1040.0,
            'Change' => 40.0,
            'Volume' => 5_000_000.0,
            'Value' => 5_200_000_000.0,
            'Frequency' => 1234.0,
            'ForeignBuy' => 2_000_000.0,
            'ForeignSell' => 500_000.0,
            'ListedShares' => 1_000_000_000.0,
            'Date' => "{$o['__date']}T00:00:00",
        ], array_diff_key($o, array_flip(['__date'])));
    }

    public function test_scrape_path_upserts_rows(): void
    {
        Process::fake([
            '*' => Process::result(output: $this->wrapperJson('2026-08-28', [
                $this->idxRow('BBCA', ['__date' => '2026-08-28']),
                $this->idxRow('TLKM', ['__date' => '2026-08-28', 'Close' => 3000.0, 'Previous' => 2900.0]),
                $this->idxRow('', ['__date' => '2026-08-28']),          // junk code -> skipped
                $this->idxRow('SUSP', ['__date' => '2026-08-28', 'Close' => 0.0]), // no trade -> skipped
            ])),
        ]);

        $this->artisan('idx:fetch-daily-summary', ['--date' => '2026-08-28'])
            ->assertExitCode(0);

        $this->assertSame(2, IdxDailySummary::whereDate('trade_date', '2026-08-28')->count());

        $bbca = IdxDailySummary::where('stock_code', 'BBCA')->firstOrFail();
        $this->assertSame(1_500_000, $bbca->foreign_net);
        $this->assertEqualsWithDelta(1_500_000 * 1040.0, (float) $bbca->foreign_net_value, 0.01);
        $this->assertEqualsWithDelta(4.0, (float) $bbca->pct_change, 0.001);
    }

    public function test_backfill_skips_weekends_and_existing_dates(): void
    {
        IdxDailySummary::create([
            'trade_date' => '2026-08-27', 'stock_code' => 'BBCA', 'close' => 1,
            'previous' => 1, 'volume' => 1, 'value' => 1, 'source' => 'existing',
        ]);

        Process::fake(['*' => Process::result(output: $this->wrapperJson('x', [$this->idxRow('BBCA', ['__date' => '2026-08-28'])]))]);

        // 2026-08-28 Fri, 2026-08-27 Thu (exists), 2026-08-26 Wed. 29/30 = weekend (from a later base).
        $this->artisan('idx:fetch-daily-summary', ['--date' => '2026-08-28', '--backfill' => 2])
            ->assertExitCode(0);

        Process::assertRanTimes(fn ($p) => in_array('--date', $p->command, true), 2); // 28 + 26, not 27
        $this->assertSame('existing', IdxDailySummary::where('stock_code', 'BBCA')->whereDate('trade_date', '2026-08-27')->value('source'));
    }

    public function test_file_option_parses_local_json_without_scraping(): void
    {
        Process::fake();
        $path = storage_path('app/testing-idx-summary.json');
        file_put_contents($path, $this->wrapperJson('2026-08-28', [$this->idxRow('ANTM', ['__date' => '2026-08-28'])]));

        $this->artisan('idx:fetch-daily-summary', ['--file' => $path])->assertExitCode(0);

        $this->assertDatabaseHas('idx_daily_summaries', ['stock_code' => 'ANTM', 'source' => 'idx_manual']);
        Process::assertNothingRan();
        @unlink($path);
    }

    public function test_reports_failure_when_scrape_returns_nonzero(): void
    {
        Process::fake(['*' => Process::result(output: '', errorOutput: 'Cloudflare block', exitCode: 1)]);

        $this->artisan('idx:fetch-daily-summary', ['--date' => '2026-08-28'])
            ->assertExitCode(1);
    }

    public function test_recover_fetches_only_missing_recent_trading_days(): void
    {
        // "Yesterday" relative to a frozen Wednesday: Tue present, Mon missing.
        $this->travelTo(Carbon::parse('2026-09-02 08:30', 'Asia/Jakarta'));

        IdxDailySummary::create([
            'trade_date' => '2026-09-01', 'stock_code' => 'BBCA', 'close' => 1,
            'previous' => 1, 'volume' => 1, 'value' => 1, 'source' => 'existing',
        ]);

        Process::fake(['*' => Process::result(output: $this->wrapperJson('x', [$this->idxRow('BBCA', ['__date' => '2026-08-31'])]))]);

        $this->artisan('idx:fetch-daily-summary', ['--recover' => true, '--recover-days' => 2])
            ->expectsOutputToContain('2026-08-31')
            ->assertExitCode(0);

        // Only the missing day was scraped; the present one was left alone.
        Process::assertRanTimes(fn ($p) => true, 1);
        $this->assertSame('existing', IdxDailySummary::whereDate('trade_date', '2026-09-01')->value('source'));
        $this->assertTrue(IdxDailySummary::whereDate('trade_date', '2026-08-31')->exists());
    }

    public function test_recover_is_a_no_op_when_all_recent_days_present(): void
    {
        $this->travelTo(Carbon::parse('2026-09-02 08:30', 'Asia/Jakarta'));
        foreach (['2026-09-01', '2026-08-31'] as $d) {
            IdxDailySummary::create([
                'trade_date' => $d, 'stock_code' => 'BBCA', 'close' => 1,
                'previous' => 1, 'volume' => 1, 'value' => 1, 'source' => 'existing',
            ]);
        }
        Process::fake();

        $this->artisan('idx:fetch-daily-summary', ['--recover' => true, '--recover-days' => 2])
            ->expectsOutputToContain('sudah lengkap')
            ->assertExitCode(0);

        Process::assertNothingRan();
    }
}
