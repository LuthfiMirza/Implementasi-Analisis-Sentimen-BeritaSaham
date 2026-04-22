<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class FetchOjkNewsCommandTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        File::delete(base_path('output/ojk_backfill_status.json'));
        File::delete(base_path('output/ojk_backfill_report.txt'));

        parent::tearDown();
    }

    public function test_command_saves_ojk_articles_as_global_macro_news(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        $rss = <<<'XML'
        <rss version="2.0">
          <channel>
            <item>
              <title>OJK keluarkan kebijakan baru untuk pasar modal</title>
              <link>https://www.ojk.go.id/id/berita/global-1</link>
              <description>Regulasi pasar modal memperkuat pengawasan emiten dan keterbukaan informasi.</description>
              <pubDate>Tue, 15 Apr 2026 08:00:00 +0700</pubDate>
            </item>
          </channel>
        </rss>
        XML;

        Http::fake([
            '*' => Http::response($rss, 200, ['Content-Type' => 'application/rss+xml']),
        ]);

        Artisan::call('news:fetch-ojk', ['--limit' => 10]);

        $article = NewsArticle::first();
        $this->assertNotNull($article);
        $this->assertNull($article->stock_id);
        $this->assertSame('ojk_rss', $article->source_provider);
        $this->assertSame('https://www.ojk.go.id/id/berita/global-1', $article->source_url);
        $this->assertGreaterThanOrEqual(0.4, (float) $article->final_quality_score);
        $this->assertFileExists(base_path('output/ojk_backfill_status.json'));
        $this->assertFileExists(base_path('output/ojk_backfill_report.txt'));

        $payload = json_decode((string) file_get_contents(base_path('output/ojk_backfill_status.json')), true);
        $this->assertSame(1, $payload['fetched_count']);
        $this->assertSame(1, $payload['saved_count']);
        $this->assertSame(1, $payload['final_article_count']);
        $this->assertSame('partial', $payload['backfill_status']);
    }

    public function test_backfill_command_is_idempotent_and_keeps_articles_global(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        $pageOne = <<<'HTML'
        <html>
          <body>
            <input type="hidden" name="__VIEWSTATE" value="state-1" />
            <input type="hidden" name="__EVENTVALIDATION" value="event-1" />
            <div class="col-lg-10">
              <div class="date">14 April 2026</div>
              <a href="/id/berita-dan-kegiatan/siaran-pers/Pages/Roadmap-Pasar-Modal.aspx" class="group-item-title">
                <strong>Siaran Pers: Roadmap Pasar Modal Berkelanjutan</strong>
              </a>
              <div class="caption">Pasar modal dan investasi berkelanjutan diperkuat oleh OJK.</div>
            </div>
            <span class="pagination">
              <span class="currentPagingButton">1</span>
            </span>
          </body>
        </html>
        HTML;

        Http::fake(function ($request) use ($pageOne) {
            $url = $request->url();

            if ($url === 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/rss') {
                return Http::response('not found', 404, ['Content-Type' => 'text/html']);
            }

            if ($url === 'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers') {
                return Http::response($pageOne, 200, ['Content-Type' => 'text/html']);
            }

            return Http::response('<html></html>', 200, ['Content-Type' => 'text/html']);
        });

        Artisan::call('news:fetch-ojk', [
            '--backfill' => true,
            '--from' => '2026-02-01',
            '--to' => '2026-04-15',
            '--limit' => 10,
            '--scan-limit' => 20,
        ]);

        Artisan::call('news:fetch-ojk', [
            '--backfill' => true,
            '--from' => '2026-02-01',
            '--to' => '2026-04-15',
            '--limit' => 10,
            '--scan-limit' => 20,
        ]);

        $this->assertSame(1, NewsArticle::where('source_provider', 'ojk_rss')->count());

        $article = NewsArticle::where('source_provider', 'ojk_rss')->first();
        $this->assertNotNull($article);
        $this->assertNull($article->stock_id);
        $this->assertSame('2026-04-14', $article->published_at?->toDateString());

        $payload = json_decode((string) file_get_contents(base_path('output/ojk_backfill_status.json')), true);
        $this->assertSame([
            'from' => '2026-02-01',
            'to' => '2026-04-15',
        ], $payload['requested_range']);
        $this->assertSame(1, $payload['final_article_count']);
        $this->assertSame('partial', $payload['backfill_status']);
    }

    public function test_backfill_command_writes_explicit_artifact_for_invalid_date_range(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia', 'is_active' => true]);

        Artisan::call('news:fetch-ojk', [
            '--backfill' => true,
            '--from' => 'not-a-date',
            '--to' => '2026-04-15',
        ]);

        $payload = json_decode((string) file_get_contents(base_path('output/ojk_backfill_status.json')), true);
        $this->assertSame('empty', $payload['backfill_status']);
        $this->assertSame('invalid_date_range', $payload['blocker_reason']);
        $this->assertSame(0, $payload['fetched_count']);
    }
}
