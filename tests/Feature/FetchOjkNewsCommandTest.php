<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class FetchOjkNewsCommandTest extends TestCase
{
    use RefreshDatabase;

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
    }
}
