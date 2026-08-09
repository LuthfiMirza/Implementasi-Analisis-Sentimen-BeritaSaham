<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Emitentrust.com -- WordPress-based Indonesian issuer/market news site. Standard WordPress RSS
 * feed at /feed/, publicly accessible, robots.txt does not disallow it -- confirmed live
 * 2026-08-09 (no login/API key required, unlike the StockBit aggregator page this was researched
 * as an alternative to; scraping a logged-in aggregator page risks ToS violation + account
 * suspension, this feed does not).
 */
class EmitentrustFetcher implements NewsFetcherInterface
{
    protected const FEED_URL = 'https://emitentrust.com/feed/';

    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $timeout = config('news.rss_timeout', env('NEWS_RSS_TIMEOUT', 8));
        $userAgent = config('news.rss_user_agent', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        try {
            $response = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1',
            ])->timeout($timeout)->get(self::FEED_URL);
        } catch (\Throwable $e) {
            Log::warning('Emitentrust request exception', ['error' => $e->getMessage()]);

            return [];
        }

        if (! $response->successful()) {
            Log::warning('Emitentrust fetch failed', ['status' => $response->status()]);

            return [];
        }

        $body = trim($response->body());
        if ($body === '') {
            return [];
        }

        $items = $this->parseFeedItems($body);
        if (! count($items)) {
            Log::warning('Emitentrust parsed 0 items');

            return [];
        }

        $articles = collect();

        foreach ($items as $item) {
            $title = (string) ($item['title'] ?? '');
            $description = (string) ($item['description'] ?? '');
            $link = (string) ($item['link'] ?? '');
            $pubDate = (string) ($item['pubDate'] ?? '');

            $titleText = strtolower($title);
            $fullText = strtolower($title.' '.$description);

            $isRelevant = count($this->mapper->directHits($stock, $titleText)) > 0
                || count($this->mapper->directHits($stock, $fullText)) > 0;

            if (! $isRelevant) {
                continue;
            }

            $articles->push([
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => 'Emitentrust',
                'source_url' => $link ?: null,
                'published_at' => $pubDate ? Carbon::parse($pubDate, 'Asia/Jakarta') : Carbon::now('Asia/Jakarta'),
                'summary' => Str::limit(strip_tags($description), 300),
                'content_snippet' => Str::limit(strip_tags($description), 300),
                'provider' => 'emitentrust',
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => ['feed' => self::FEED_URL, 'title' => $title, 'description' => $description],
            ]);
        }

        return $articles->sortByDesc('published_at')->take($limit)->values()->all();
    }

    protected function parseFeedItems(string $xmlString): array
    {
        libxml_use_internal_errors(true);
        $xml = @simplexml_load_string($xmlString);
        $errors = libxml_get_errors();
        libxml_clear_errors();

        if (! $xml || $errors) {
            Log::warning('Emitentrust invalid XML', [
                'errors' => collect($errors)->pluck('message')->take(2)->all(),
            ]);

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
                ];
            }
        }

        return $items;
    }
}
