<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class GoogleNewsRssFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $baseUrl = (string) config('news.google_news_rss.base_url', 'https://news.google.com/rss/search');
        $hl = (string) config('news.google_news_rss.hl', 'id');
        $gl = (string) config('news.google_news_rss.gl', 'ID');
        $ceid = (string) config('news.google_news_rss.ceid', 'ID:id');
        $timeout = (int) config('news.google_news_rss.timeout', config('news.rss_timeout', 8));
        $userAgent = (string) config('news.google_news_rss.user_agent', config('news.rss_user_agent', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        $articles = collect();
        foreach ($this->buildQueries($stock) as $query) {
            try {
                $response = Http::withHeaders([
                    'User-Agent' => $userAgent,
                    'Accept' => 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1',
                ])->timeout($timeout)->get($baseUrl, [
                    'q' => $query,
                    'hl' => $hl,
                    'gl' => $gl,
                    'ceid' => $ceid,
                ]);
            } catch (\Throwable $e) {
                Log::warning('Google News RSS request failed', ['query' => $query, 'error' => $e->getMessage()]);
                continue;
            }

            if (! $response->successful()) {
                Log::warning('Google News RSS response error', [
                    'status' => $response->status(),
                    'query' => $query,
                ]);
                continue;
            }

            $articles = $articles->merge($this->parseFeed($response->body(), $stock, $query));
        }

        return $this->prioritizeDateCoverage($articles, $limit)
            ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
            ->values()
            ->all();
    }

    /**
     * @return array<int, string>
     */
    protected function buildQueries(Stock $stock): array
    {
        $primaryAlias = $this->mapper->primarySearchAlias($stock);
        $queries = [
            '"'.$primaryAlias.'"',
            '"saham '.$stock->code.'"',
            '"emiten '.$stock->code.'"',
        ];

        foreach ($this->mapper->exactSearchQueries($stock, 4) as $query) {
            $queries[] = '"'.$query.'"';
        }

        return collect($queries)
            ->filter(fn ($query) => trim((string) $query) !== '')
            ->unique()
            ->values()
            ->all();
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    protected function parseFeed(string $xmlString, Stock $stock, string $query): array
    {
        libxml_use_internal_errors(true);
        $xml = @simplexml_load_string($xmlString);
        $errors = libxml_get_errors();
        libxml_clear_errors();

        if (! $xml || $errors) {
            Log::warning('Google News RSS invalid XML', [
                'query' => $query,
                'errors' => collect($errors)->pluck('message')->take(2)->all(),
            ]);
            return [];
        }

        $items = collect();
        foreach ($xml->channel->item ?? [] as $item) {
            $title = trim((string) ($item->title ?? ''));
            $description = html_entity_decode(strip_tags((string) ($item->description ?? '')));
            $combinedText = trim($title.' '.$description);
            if ($title === '' || count($this->mapper->directHits($stock, $combinedText)) === 0) {
                continue;
            }

            $link = trim((string) ($item->link ?? ''));
            $sourceName = trim((string) ($item->source ?? 'Google News'));
            $publishedAt = trim((string) ($item->pubDate ?? ''));

            $items->push([
                'provider' => 'google_news_rss',
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => $sourceName ?: 'Google News',
                'source_url' => $this->normalizeSourceUrl($link),
                'published_at' => $publishedAt ? Carbon::parse($publishedAt) : Carbon::now(),
                'summary' => Str::limit($description, 300),
                'content_snippet' => Str::limit($description, 500),
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => [
                    'query' => $query,
                    'title' => $title,
                    'description' => $description,
                    'link' => $link,
                    'source' => $sourceName,
                ],
            ]);
        }

        return $items->all();
    }

    protected function normalizeSourceUrl(?string $url): ?string
    {
        $url = trim((string) $url);
        if ($url === '') {
            return null;
        }

        if (mb_strlen($url) <= 240) {
            return $url;
        }

        return 'https://news.google.com/rss/articles/'.substr(sha1($url), 0, 32);
    }

    protected function prioritizeDateCoverage(Collection $articles, int $limit): Collection
    {
        $sorted = $articles
            ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
            ->sortByDesc('published_at')
            ->values();

        if ($limit <= 0 || $sorted->count() <= $limit) {
            return $sorted;
        }

        $selected = collect();
        $seenDates = [];

        foreach ($sorted as $article) {
            $dateKey = optional($article['published_at'] ?? null)?->toDateString() ?? 'unknown';
            if (isset($seenDates[$dateKey])) {
                continue;
            }

            $seenDates[$dateKey] = true;
            $selected->push($article);
            if ($selected->count() >= $limit) {
                return $selected;
            }
        }

        foreach ($sorted as $article) {
            $selected->push($article);
            $selected = $selected
                ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
                ->values();
            if ($selected->count() >= $limit) {
                break;
            }
        }

        return $selected->take($limit)->values();
    }
}
