<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\Trade;
use App\Models\User;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class DetectDrawdownBounceSignalCommandTest extends TestCase
{
    private string $newsCachePath;

    protected function setUp(): void
    {
        parent::setUp();

        // user_id=2 dipakai hardcoded di DetectDrawdownBounceSignalCommand (konsisten dengan
        // konvensi baris SIMULASI BACKTEST lama yang juga pakai user_id=2) -- di DB dev/prod
        // nyata itu akun demo user@sentimena.test, di test DB kosong harus di-seed manual.
        User::factory()->create(['id' => 2]);

        $this->newsCachePath = base_path('quant/drawdown_bounce_tracker/news_context_cache.json');
    }

    protected function tearDown(): void
    {
        // Fase DG: news_context_cache.json ditulis command ini ke path REAL (dibaca
        // detect_signal.py produksi) -- WAJIB dibersihkan setelah test, jangan sampai isi test
        // (mis. ticker BUMI dgn 1 artikel dummy) "bocor" ke run production berikutnya. Pola sama
        // persis pelajaran Fase DF (snoozed_alerts.json).
        if (is_file($this->newsCachePath)) {
            unlink($this->newsCachePath);
        }

        parent::tearDown();
    }

    public function test_successful_run_surfaces_script_output(): void
    {
        Process::fake([
            '*' => Process::result(output: "SIGNAL BARU: BUMI (tracked) trigger 2026-08-03 -> entry 2026-08-04 @ 160\n"
                ."1 sinyal baru dicatat. Total tercatat: 1.\n"),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('SIGNAL BARU')
            ->expectsOutputToContain('sinyal baru dicatat')
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            return str_contains(implode(' ', $process->command), 'detect_signal.py');
        });
    }

    public function test_sync_open_line_creates_live_trade_journal_entry(): void
    {
        Stock::factory()->create(['code' => 'BUMI']);

        Process::fake([
            '*' => Process::result(output: "SIGNAL BARU: BUMI (tracked) trigger 2026-08-11 -> entry 2026-08-12 @ 178\n"
                ."SYNC_OPEN|BUMI|178|2026-08-12|GABUNGAN|ret2d\n"
                .'1 sinyal drawdown-bounce baru dicatat. Total tercatat: 1.'),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);

        $trade = Trade::where('ticker', 'BUMI')->where('status', 'open')->first();
        $this->assertNotNull($trade);
        $this->assertEquals(178, $trade->entry_price);
        $this->assertSame('2026-08-12', $trade->entry_date->toDateString());
        $this->assertStringContainsString('LIVE', $trade->notes);
        $this->assertStringContainsString('GABUNGAN', $trade->notes);
    }

    public function test_sync_open_is_idempotent_on_rerun(): void
    {
        Stock::factory()->create(['code' => 'DEWA']);

        Process::fake([
            '*' => Process::result(output: 'SYNC_OPEN|DEWA|442|2026-08-12|MOMENTUM|rsi64'),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);
        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);

        $this->assertSame(1, Trade::where('ticker', 'DEWA')->where('status', 'open')->count());
    }

    public function test_sync_open_skipped_gracefully_when_stock_unknown(): void
    {
        Process::fake([
            '*' => Process::result(output: 'SYNC_OPEN|ZZZZ|100|2026-08-12|GABUNGAN|ret2d'),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('tidak ditemukan di tabel stocks')
            ->assertExitCode(0);

        $this->assertDatabaseMissing('trades', ['ticker' => 'ZZZZ']);
    }

    public function test_no_new_signal_still_exits_successfully(): void
    {
        Process::fake([
            '*' => Process::result(output: "Tidak ada sinyal baru. Tidak ada trigger sejak 2026-07-31. Total tercatat: 0.\n"),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('Tidak ada sinyal baru')
            ->assertExitCode(0);
    }

    // Fase DG: News-in-Signal -- cache berita+sentimen per ticker ditulis SEBELUM python script
    // jalan, dibaca detect_signal.py buat lampirkan konteks berita ke alert.
    public function test_news_context_cache_is_written_before_script_runs(): void
    {
        Process::fake(['*' => Process::result(output: 'Tidak ada sinyal baru.')]);

        $stock = Stock::factory()->create(['code' => 'BUMI']);
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'title' => 'BUMI raih kontrak baru',
            'sentiment_label' => 'positive',
            'published_at' => now()->subHours(2),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);

        $this->assertFileExists($this->newsCachePath);
        $cache = json_decode(file_get_contents($this->newsCachePath), true);
        $this->assertArrayHasKey('BUMI', $cache);
        $this->assertCount(1, $cache['BUMI']);
        $this->assertSame('BUMI raih kontrak baru', $cache['BUMI'][0]['title']);
        $this->assertSame('positive', $cache['BUMI'][0]['sentiment']);
    }

    public function test_news_context_cache_limits_to_3_most_recent_articles_per_ticker(): void
    {
        Process::fake(['*' => Process::result(output: 'Tidak ada sinyal baru.')]);

        $stock = Stock::factory()->create(['code' => 'DEWA']);
        foreach (range(1, 5) as $i) {
            NewsArticle::factory()->create([
                'stock_id' => $stock->id,
                'title' => "Berita DEWA ke-{$i}",
                'sentiment_label' => 'neutral',
                'published_at' => now()->subDays($i),
            ]);
        }

        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);

        $cache = json_decode(file_get_contents($this->newsCachePath), true);
        $this->assertCount(3, $cache['DEWA']);
        // Paling baru (subDays(1)) harus di urutan PERTAMA.
        $this->assertSame('Berita DEWA ke-1', $cache['DEWA'][0]['title']);
    }

    public function test_news_context_cache_is_empty_array_for_ticker_with_no_articles(): void
    {
        Process::fake(['*' => Process::result(output: 'Tidak ada sinyal baru.')]);

        $this->artisan('research:detect-drawdown-bounce-signal')->assertExitCode(0);

        $cache = json_decode(file_get_contents($this->newsCachePath), true);
        $this->assertArrayHasKey('BUMI', $cache);
        $this->assertSame([], $cache['BUMI']);
    }

    public function test_failed_fetch_reports_error_and_nonzero_exit(): void
    {
        Process::fake([
            '*' => Process::result(output: '', errorOutput: 'yfinance timeout', exitCode: 1),
        ]);

        $this->artisan('research:detect-drawdown-bounce-signal')
            ->expectsOutputToContain('Gagal mendeteksi sinyal')
            ->assertExitCode(1);
    }
}
