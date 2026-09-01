<?php

namespace Tests\Feature;

use App\Models\KseiOwnership;
use Tests\TestCase;

class FetchKseiOwnershipCommandTest extends TestCase
{
    private string $path;

    protected function setUp(): void
    {
        parent::setUp();
        $this->path = storage_path('app/testing-ksei.csv');
    }

    protected function tearDown(): void
    {
        @unlink($this->path);
        parent::tearDown();
    }

    /** KSEI "Balance Position" shape: Code, Name, then Local/Foreign sub-columns the parser sums. */
    private function writeCsv(array $rows): void
    {
        $lines = ['Code,Name,Local CP,Local ID,Local OT,Foreign CP,Foreign ID,Foreign OT'];
        foreach ($rows as [$code, $name, $local, $foreign]) {
            $lines[] = implode(',', [
                $code, '"'.$name.'"',
                (int) ($local * 0.6), (int) ($local * 0.3), $local - (int) ($local * 0.6) - (int) ($local * 0.3),
                (int) ($foreign * 0.6), (int) ($foreign * 0.3), $foreign - (int) ($foreign * 0.6) - (int) ($foreign * 0.3),
            ]);
        }
        file_put_contents($this->path, implode("\n", $lines)."\n");
    }

    public function test_requires_a_file(): void
    {
        $this->artisan('ksei:fetch-ownership')->assertExitCode(1);
    }

    public function test_imports_a_snapshot_and_sums_local_and_foreign_subcolumns(): void
    {
        $this->writeCsv([
            ['BBCA', 'Bank Central Asia Tbk.', 71_000_000, 29_000_000], // 29% foreign
            ['INDF', 'Indofood Sukses Makmur Tbk.', 52_000_000, 48_000_000],
            ['', 'junk row', 1, 1],
        ]);

        $this->artisan('ksei:fetch-ownership', ['--file' => $this->path, '--date' => '2026-06-30'])
            ->assertExitCode(0);

        $this->assertSame(2, KseiOwnership::whereDate('snapshot_date', '2026-06-30')->count());

        $bbca = KseiOwnership::where('stock_code', 'BBCA')->firstOrFail();
        $this->assertEqualsWithDelta(29.0, (float) $bbca->foreign_pct, 0.01);
        $this->assertEqualsWithDelta(71.0, (float) $bbca->local_pct, 0.01);
        $this->assertNull($bbca->foreign_pct_delta); // no prior snapshot
        $this->assertSame('ksei_manual', $bbca->source);
    }

    public function test_computes_month_over_month_foreign_delta(): void
    {
        $this->writeCsv([['ADRO', 'Alamtri Resources Indonesia Tbk.', 82_000_000, 18_000_000]]); // 18%
        $this->artisan('ksei:fetch-ownership', ['--file' => $this->path, '--date' => '2026-06-30'])->assertExitCode(0);

        $this->writeCsv([['ADRO', 'Alamtri Resources Indonesia Tbk.', 79_500_000, 20_500_000]]); // 20.5%
        $this->artisan('ksei:fetch-ownership', ['--file' => $this->path, '--date' => '2026-07-31'])
            ->expectsOutputToContain('delta MoM vs 2026-06-30')
            ->assertExitCode(0);

        $july = KseiOwnership::where('stock_code', 'ADRO')->whereDate('snapshot_date', '2026-07-31')->firstOrFail();
        $this->assertEqualsWithDelta(2.5, (float) $july->foreign_pct_delta, 0.01);
    }

    public function test_source_flag_tags_synthetic_data(): void
    {
        $this->writeCsv([['BBRI', 'Bank Rakyat Indonesia (Persero) Tbk.', 68_000_000, 32_000_000]]);

        $this->artisan('ksei:fetch-ownership', [
            '--file' => $this->path, '--date' => '2026-06-30', '--source' => 'ksei_sample',
        ])->expectsOutputToContain('bukan data KSEI asli')->assertExitCode(0);

        $this->assertSame('ksei_sample', KseiOwnership::where('stock_code', 'BBRI')->value('source'));
    }

    public function test_existing_snapshot_is_not_overwritten_without_force(): void
    {
        $this->writeCsv([['TLKM', 'Telkom Indonesia (Persero) Tbk.', 76_000_000, 24_000_000]]);
        $this->artisan('ksei:fetch-ownership', ['--file' => $this->path, '--date' => '2026-06-30'])->assertExitCode(0);

        $this->writeCsv([['TLKM', 'Telkom Indonesia (Persero) Tbk.', 50_000_000, 50_000_000]]);
        $this->artisan('ksei:fetch-ownership', ['--file' => $this->path, '--date' => '2026-06-30'])
            ->expectsOutputToContain('sudah ada')
            ->assertExitCode(0);

        $this->assertEqualsWithDelta(24.0, (float) KseiOwnership::where('stock_code', 'TLKM')->value('foreign_pct'), 0.01);
    }
}
