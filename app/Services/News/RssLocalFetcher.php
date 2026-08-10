<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class RssLocalFetcher implements NewsFetcherInterface
{
    protected const DEFAULT_FEEDS = [
        // Antara keeps the broadest free Indonesia business/market RSS coverage.
        'https://www.antaranews.com/rss/ekonomi.xml',
        'https://www.antaranews.com/rss/ekonomi-finansial.xml',
        'https://www.antaranews.com/rss/ekonomi-bisnis.xml',
        'https://www.antaranews.com/rss/ekonomi-bursa.xml',
        // CNBC Indonesia contributes corporate and macro market headlines.
        'https://www.cnbcindonesia.com/market/rss',
        'https://www.cnbcindonesia.com/news/rss',
        'https://www.cnbcindonesia.com/tech/rss',
        // detikFinance helps fill local issuer and macro policy coverage gaps.
        'https://finance.detik.com/bursa-dan-valas/rss',
        'https://finance.detik.com/moneter/rss',
        // Katadata often covers corporate and capital-market developments around listed issuers.
        // Live-verified 2026-07-31: old '/feed' URL now redirects (307) to an HTML page instead of
        // XML; '/rss/finansial' still serves real RSS with current items.
        'https://katadata.co.id/rss/finansial',
        // IDX Channel is IDX-affiliated media with frequent per-issuer market news.
        'https://www.idxchannel.com/rss',
        // CNN Indonesia adds macro/economy coverage that complements the issuer-focused feeds above.
        'https://www.cnnindonesia.com/ekonomi/rss',
        // Bloomberg Technoz frequently covers issuer-level corporate actions and market moves.
        'https://www.bloombergtechnoz.com/rss',
        // Tempo Bisnis broadens business-desk coverage beyond the portals above.
        'https://rss.tempo.co/bisnis',
        // Republika Ekonomi adds another independent macro/regulatory news source.
        'https://www.republika.co.id/rss/ekonomi',
    ];

    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $feeds = $this->feeds();
        if (! count($feeds)) {
            return [];
        }

        $articles = collect();
        $timeout = config('news.rss_timeout', env('NEWS_RSS_TIMEOUT', 8));
        $userAgent = config('news.rss_user_agent', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        foreach ($feeds as $feedUrl) {
            try {
                $resp = Http::withHeaders([
                    'User-Agent' => $userAgent,
                    'Accept' => 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1',
                ])->timeout($timeout)->get($feedUrl);
            } catch (\Throwable $e) {
                // One slow/unreachable feed (of ~16) must not abort every other feed for this
                // stock -- an uncaught exception here bubbles all the way up through
                // NewsAggregationService::refreshFromProvider() and kills every OTHER provider's
                // results for this stock too, not just rss_local's. Confirmed live: rss.tempo.co
                // timing out silently discarded a full multi-provider fetch for BBCA and TLKM.
                Log::warning('RSS request exception', ['feed' => $feedUrl, 'error' => $e->getMessage()]);
                continue;
            }

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

                $isRelevant = count($this->mapper->directHits($stock, $titleText)) > 0
                    || count($this->mapper->directHits($stock, $fullText)) > 0;

                if (! $isRelevant) {
                    continue;
                }

                $articles->push([
                    'title' => $title,
                    'slug' => Str::slug($title).'-'.Str::random(4),
                    'source_name' => $item['source'] ?? (parse_url($feedUrl, PHP_URL_HOST) ?: 'RSS'),
                    'source_url' => $link ?: null,
                    'image_url' => $item['image'] ?? null,
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
        $custom = collect(preg_split('/[;,]/', $env))
            ->map(fn ($f) => trim($f))
            ->filter()
            ->all();

        return collect(array_merge(self::DEFAULT_FEEDS, $custom))->unique()->values()->all();
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
                    'image' => $this->extractImageFromRssItem($item),
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
                    'image' => $this->extractImageFromRssItem($item),
                ];
            }
        }

        return $items;
    }

    /**
     * Sebagian besar feed sudah bawa gambar sendiri lewat <enclosure type="image/..."> atau
     * <media:content> (namespace MRSS) -- data ini sudah ada di RSS mentah, tidak perlu request
     * tambahan ke halaman artikel seperti business_site_search. Katadata & Tempo RSS TIDAK punya
     * tag ini sama sekali (dicek langsung di feed mentah) -- null untuk keduanya itu valid,
     * bukan bug.
     */
    protected function extractImageFromRssItem(\SimpleXMLElement $item): ?string
    {
        if (isset($item->enclosure)) {
            $type = (string) ($item->enclosure['type'] ?? '');
            $url = (string) ($item->enclosure['url'] ?? '');
            if ($url !== '' && ($type === '' || str_starts_with($type, 'image'))) {
                return $url;
            }
        }

        $media = $item->children('http://search.yahoo.com/mrss/');
        if (isset($media->content)) {
            $url = (string) ($media->content['url'] ?? '');
            if ($url !== '') {
                return $url;
            }
        }
        if (isset($media->thumbnail)) {
            $url = (string) ($media->thumbnail['url'] ?? '');
            if ($url !== '') {
                return $url;
            }
        }

        return null;
    }
}
