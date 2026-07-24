<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use fivefilters\Readability\Configuration;
use fivefilters\Readability\ParseException;
use fivefilters\Readability\Readability;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

/**
 * Fase R7a: backfills news_articles.full_text by fetching source_url and extracting the article
 * body with fivefilters/readability.php. Only ojk_rss (90 rows) had full_text natively; the other
 * ~1786 rows (google_news_rss, rss_local, gnews, newsapi, business_site_search) store null. For
 * google_news_rss specifically, source_url is a Google redirect link, not the publisher URL --
 * run `news:resolve-google-news-urls` first so this command has a fetchable URL to work with
 * (rows still pointing at news.google.com are skipped here rather than re-implementing that
 * resolution logic).
 */
class ScrapeArticleFullTextCommand extends Command
{
    protected $signature = 'news:scrape-full-text
        {--limit=100 : Maximum rows to process this run}
        {--dry-run : Extract and report without saving}
        {--provider=* : Restrict to specific source_provider values}
        {--min-length=200 : Minimum extracted body length to accept (chars)}';

    protected $description = 'Backfill news_articles.full_text by fetching source_url and extracting the article body.';

    public function handle(): int
    {
        $limit = max(1, (int) $this->option('limit'));
        $dryRun = (bool) $this->option('dry-run');
        $minLength = max(1, (int) $this->option('min-length'));
        $providers = collect($this->option('provider'))->filter()->values();

        $query = NewsArticle::query()
            ->whereNotNull('source_url')
            ->where(function ($q) {
                $q->whereNull('full_text')->orWhere('full_text', '');
            })
            ->where('source_url', 'not like', 'https://news.google.com/%');

        if ($providers->isNotEmpty()) {
            $query->whereIn('source_provider', $providers->all());
        }

        $articles = $query->orderByDesc('published_at')->limit($limit)->get();

        if ($articles->isEmpty()) {
            $this->info('Tidak ada artikel yang memenuhi kriteria (cek dulu news:resolve-google-news-urls kalau providernya google_news_rss).');

            return self::SUCCESS;
        }

        $fetched = 0;
        $saved = 0;
        $tooShort = 0;
        $failed = 0;

        foreach ($articles as $article) {
            $result = $this->scrapeOne($article->source_url);

            if ($result === null) {
                $failed++;
                $this->warn("[gagal] {$article->id} {$article->source_url}");
                usleep(300_000);

                continue;
            }

            $fetched++;

            if (mb_strlen($result) < $minLength) {
                $tooShort++;
                $this->line("[terlalu pendek, ".mb_strlen($result)." char] {$article->id} {$article->source_url}");
                usleep(300_000);

                continue;
            }

            $this->line("[ok, ".mb_strlen($result)." char] {$article->id} {$article->source_url}");

            if (! $dryRun) {
                $article->forceFill(['full_text' => $result])->save();
                $saved++;
            }

            usleep(300_000);
        }

        $this->info(($dryRun ? '[dry-run] ' : '')."Selesai: {$articles->count()} diproses, {$fetched} berhasil fetch, {$saved} disimpan, {$tooShort} terlalu pendek, {$failed} gagal.");

        return self::SUCCESS;
    }

    protected function scrapeOne(string $url): ?string
    {
        try {
            $response = Http::withHeaders([
                'User-Agent' => (string) config('news.rss_user_agent', 'SentimenaBot/1.0 (+https://sentimena.app)'),
                'Accept' => 'text/html,application/xhtml+xml',
            ])->timeout((int) config('news.rss_timeout', 8))->get($url);
        } catch (\Throwable $e) {
            return null;
        }

        if (! $response->successful() || $response->body() === '') {
            return null;
        }

        $configuration = new Configuration();
        $configuration->setSummonCthulhu(true);
        $readability = new Readability($configuration);

        try {
            $readability->parse($response->body());
        } catch (ParseException $e) {
            return null;
        }

        $text = trim(strip_tags($readability->getContent() ?? ''));
        $text = preg_replace('/\s+/u', ' ', $text) ?? $text;

        return $text === '' ? null : Str::limit($text, 8000, '');
    }
}
