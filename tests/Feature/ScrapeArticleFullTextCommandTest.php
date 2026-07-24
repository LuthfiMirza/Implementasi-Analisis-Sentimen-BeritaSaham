<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ScrapeArticleFullTextCommandTest extends TestCase
{
    use RefreshDatabase;

    protected function longArticleHtml(string $body): string
    {
        return '<html><head><title>Judul Berita</title></head><body><article><h1>Judul Berita</h1><p>'.$body.'</p></article></body></html>';
    }

    public function test_it_fetches_and_saves_full_text_for_articles_missing_it(): void
    {
        $paragraph = str_repeat('Ini adalah kalimat berita yang cukup panjang untuk lolos ambang batas. ', 10);

        $article = NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://example.com/berita/satu',
            'full_text' => null,
        ]);

        Http::fake([
            'example.com/*' => Http::response($this->longArticleHtml($paragraph), 200),
        ]);

        $this->artisan('news:scrape-full-text', ['--limit' => 10])
            ->assertExitCode(0);

        $article->refresh();
        $this->assertNotNull($article->full_text);
        $this->assertStringContainsString('kalimat berita', $article->full_text);
    }

    public function test_dry_run_does_not_persist_changes(): void
    {
        $paragraph = str_repeat('Ini adalah kalimat berita yang cukup panjang untuk lolos ambang batas. ', 10);

        $article = NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://example.com/berita/dua',
            'full_text' => null,
        ]);

        Http::fake([
            'example.com/*' => Http::response($this->longArticleHtml($paragraph), 200),
        ]);

        $this->artisan('news:scrape-full-text', ['--limit' => 10, '--dry-run' => true])
            ->assertExitCode(0);

        $article->refresh();
        $this->assertNull($article->full_text);
    }

    public function test_it_skips_articles_that_already_have_full_text(): void
    {
        NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://example.com/berita/sudah-ada',
            'full_text' => 'Sudah ada teks lengkap sebelumnya.',
        ]);

        Http::fake();

        $this->artisan('news:scrape-full-text', ['--limit' => 10])
            ->assertExitCode(0);

        Http::assertNothingSent();
    }

    public function test_it_skips_unresolved_google_news_redirect_urls(): void
    {
        NewsArticle::factory()->create([
            'source_provider' => 'google_news_rss',
            'source_url' => 'https://news.google.com/rss/articles/abc123',
            'full_text' => null,
        ]);

        Http::fake();

        $this->artisan('news:scrape-full-text', ['--limit' => 10])
            ->assertExitCode(0);

        Http::assertNothingSent();
    }

    public function test_it_tolerates_fetch_failures_and_continues(): void
    {
        $paragraph = str_repeat('Ini adalah kalimat berita yang cukup panjang untuk lolos ambang batas. ', 10);

        NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://broken.example.com/berita',
            'full_text' => null,
        ]);
        $good = NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://good.example.com/berita',
            'full_text' => null,
        ]);

        Http::fake([
            'broken.example.com/*' => Http::response('', 500),
            'good.example.com/*' => Http::response($this->longArticleHtml($paragraph), 200),
        ]);

        $this->artisan('news:scrape-full-text', ['--limit' => 10])
            ->assertExitCode(0);

        $good->refresh();
        $this->assertNotNull($good->full_text);
    }

    public function test_it_rejects_extracted_text_shorter_than_min_length(): void
    {
        $article = NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://example.com/berita/pendek',
            'full_text' => null,
        ]);

        Http::fake([
            'example.com/*' => Http::response($this->longArticleHtml('Teks pendek saja.'), 200),
        ]);

        $this->artisan('news:scrape-full-text', ['--limit' => 10, '--min-length' => 500])
            ->assertExitCode(0);

        $article->refresh();
        $this->assertNull($article->full_text);
    }

    public function test_provider_option_restricts_scope(): void
    {
        $paragraph = str_repeat('Ini adalah kalimat berita yang cukup panjang untuk lolos ambang batas. ', 10);

        $rssLocal = NewsArticle::factory()->create([
            'source_provider' => 'rss_local',
            'source_url' => 'https://example.com/berita/rss-local',
            'full_text' => null,
        ]);
        $gnews = NewsArticle::factory()->create([
            'source_provider' => 'gnews',
            'source_url' => 'https://example.com/berita/gnews',
            'full_text' => null,
        ]);

        Http::fake([
            'example.com/*' => Http::response($this->longArticleHtml($paragraph), 200),
        ]);

        $this->artisan('news:scrape-full-text', ['--limit' => 10, '--provider' => ['gnews']])
            ->assertExitCode(0);

        $rssLocal->refresh();
        $gnews->refresh();
        $this->assertNull($rssLocal->full_text);
        $this->assertNotNull($gnews->full_text);
    }
}
