<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class RssLocalFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $feeds = $this->feeds();
        if (! count($feeds)) {
            return [];
        }

        $keywords = $this->mapper->keywords($stock);
        $articles = collect();
        $timeout = config('news.rss_timeout', env('NEWS_RSS_TIMEOUT', 8));
        $userAgent = config('news.rss_user_agent', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        foreach ($feeds as $feedUrl) {
            $resp = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1',
            ])->timeout($timeout)->get($feedUrl);

            if (! $resp->successful()) {
                Log::warning('RSS fetch failed', ['feed' => $feedUrl, 'status' => $resp->status()]);
                continue;
            }

            $body = trim($resp->body());
            if ($body === '') {
                Log::warning('RSS empty body', ['feed' => $feedUrl]);
                continue;
            }

            $contentType = strtolower($resp->header('Content-Type') ?? '');
            if (str_contains($contentType, 'html') || stripos($body, '<html') !== false) {
                Log::warning('RSS returned HTML, skipped', ['feed' => $feedUrl]);
                continue;
            }

            $items = $this->parseFeedItems($body, $feedUrl);
            if (! count($items)) {
                Log::warning('RSS parsed 0 items', ['feed' => $feedUrl]);
                continue;
            }

            foreach ($items as $item) {
                $title = (string) ($item['title'] ?? '');
                $description = (string) ($item['description'] ?? '');
                $link = (string) ($item['link'] ?? '');
                $pubDate = (string) ($item['pubDate'] ?? '');

                $titleText = strtolower($title);
                $fullText = strtolower($title.' '.$description);

                $isRelevant = collect($keywords)->contains(fn ($kw) => Str::contains($titleText, strtolower($kw)));
                if (! $isRelevant) {
                    $isRelevant = Str::contains($fullText, strtolower($stock->code));
                }
                if (! $isRelevant) {
                    $isRelevant = collect($keywords)->contains(fn ($kw) => Str::contains($fullText, strtolower($kw)));
                }

                if (! $isRelevant) {
                    $financialKeywords = [
                        'saham', 'bursa', 'ihsg', 'bank', 'investasi',
                        'laba', 'dividen', 'emiten', 'idx', 'bei',
                        'keuangan', 'pasar modal', 'obligasi',
                    ];
                    $hits = collect($financialKeywords)->filter(fn ($kw) => Str::contains($fullText, $kw))->count();
                    $isRelevant = $hits >= 2;
                }

                if (! $isRelevant) {
                    continue;
                }

                $articles->push([
                    'title' => $title,
                    'slug' => Str::slug($title).'-'.Str::random(4),
                    'source_name' => $item['source'] ?? (parse_url($feedUrl, PHP_URL_HOST) ?: 'RSS'),
                    'source_url' => $link ?: null,
                    'published_at' => $pubDate ? Carbon::parse($pubDate, 'Asia/Jakarta') : Carbon::now('Asia/Jakarta'),
                    'summary' => Str::limit(strip_tags($description), 300),
                    'content_snippet' => Str::limit(strip_tags($description), 300),
                    'provider' => 'rss_local',
                    'sentiment_label' => null,
                    'sentiment_score' => null,
                    'raw_payload' => ['feed' => $feedUrl, 'title' => $title, 'description' => $description],
                ]);
            }
        }

        return $articles->sortByDesc('published_at')->take($limit)->values()->all();
    }

    protected function feeds(): array
    {
        $env = env('NEWS_RSS_SOURCES', '');
        $defaults = [
            'https://www.cnbcindonesia.com/market/rss',
            'https://www.cnbcindonesia.com/tech/rss',
            'https://www.cnbcindonesia.com/news/rss',
            'https://finance.detik.com/bursa-dan-valas/rss',
            'https://finance.detik.com/moneter/rss',
        ];

        $custom = collect(preg_split('/[;,]/', $env))
            ->map(fn ($f) => trim($f))
            ->filter()
            ->all();

        return collect($custom ?: $defaults)->unique()->values()->all();
    }

    protected function parseFeedItems(string $xmlString, string $feedUrl): array
    {
        libxml_use_internal_errors(true);
        $xml = @simplexml_load_string($xmlString);
        $errors = libxml_get_errors();
        libxml_clear_errors();
        if (! $xml || $errors) {
            Log::warning('RSS invalid XML', ['feed' => $feedUrl, 'errors' => collect($errors)->pluck('message')->take(2)->all()]);
            return [];
        }

        $items = [];
        if (isset($xml->channel->item)) {
            foreach ($xml->channel->item as $item) {
                $items[] = [
                    'title' => (string) $item->title,
                    'description' => (string) ($item->description ?? ''),
                    'link' => (string) ($item->link ?? ''),
                    'pubDate' => (string) ($item->pubDate ?? ''),
                    'source' => (string) ($item->source ?? ''),
                ];
            }
        } elseif (isset($xml->entry)) {
            foreach ($xml->entry as $item) {
                $items[] = [
                    'title' => (string) $item->title,
                    'description' => (string) ($item->summary ?? ''),
                    'link' => (string) (isset($item->link['href']) ? $item->link['href'] : ($item->link ?? '')),
                    'pubDate' => (string) ($item->updated ?? $item->published ?? ''),
                    'source' => (string) ($item->author->name ?? ''),
                ];
            }
        }

        return $items;
    }
}
