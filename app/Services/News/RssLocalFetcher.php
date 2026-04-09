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

        foreach ($feeds as $feedUrl) {
            $resp = Http::withHeaders([
                'User-Agent' => 'Sentimena/1.0 (+https://sentimena.local)',
            ])->get($feedUrl);
            if (! $resp->successful()) {
                Log::warning('RSS fetch failed', ['feed' => $feedUrl, 'status' => $resp->status()]);
                continue;
            }
            $items = $this->parseFeedItems($resp->body());
            if (! count($items)) {
                continue;
            }

            foreach ($items as $item) {
                $title = (string) ($item['title'] ?? '');
                $description = (string) ($item['description'] ?? '');
                $link = (string) ($item['link'] ?? '');
                $pubDate = (string) ($item['pubDate'] ?? '');

                // filter relevansi
                $text = strtolower($title.' '.$description);
                $isRelevant = collect($keywords)->contains(function ($kw) use ($text) {
                    return Str::contains($text, strtolower($kw));
                });
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
            'https://www.kontan.co.id/rss/finansial',
            'https://www.bisnis.com/rss/finansial',
        ];

        $custom = collect(preg_split('/[;,]/', $env))
            ->map(fn ($f) => trim($f))
            ->filter()
            ->all();

        return collect($custom ?: $defaults)->unique()->values()->all();
    }

    protected function parseFeedItems(string $xmlString): array
    {
        $xml = @simplexml_load_string($xmlString);
        if (! $xml) {
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
                    'link' => (string) optional($item->link)['href'] ?? '',
                    'pubDate' => (string) ($item->updated ?? $item->published ?? ''),
                    'source' => (string) ($item->author->name ?? ''),
                ];
            }
        }

        return $items;
    }
}
