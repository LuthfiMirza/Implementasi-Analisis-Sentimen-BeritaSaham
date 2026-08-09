<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Currents API (currentsapi.services) -- free tier 1,000 requests/day, Indonesian language
 * support. One additional source alongside gnews/newsapi, not a replacement for google_news_rss
 * (dead end, R7a) or gdelt (rate-limited, R7a); its own free-tier ceiling makes it a marginal
 * volume addition, not a structural fix to full_text coverage.
 */
class CurrentsFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $apiKey = config('services.currents.api_key');
        $baseUrl = config('services.currents.api_base_url', 'https://api.currentsapi.services/v1/search');
        $language = config('services.currents.language', 'id');
        $timeout = (int) config('services.currents.timeout', 8);
        $userAgent = config('services.currents.user_agent', 'SentimenaNews/1.0');

        if (! $apiKey) {
            return [];
        }

        $query = $this->mapper->queryString($stock);
        $articles = collect();

        try {
            $response = Http::withHeaders(['User-Agent' => $userAgent])
                ->timeout($timeout)
                ->get($baseUrl, [
                    'apiKey' => $apiKey,
                    'query' => $query,
                    'language' => $language,
                    'page_size' => min(max($limit, 1), 200),
                ]);
        } catch (\Throwable $e) {
            Log::warning('Currents request exception', ['error' => $e->getMessage()]);
            return [];
        }

        if (! $response->successful()) {
            Log::warning('Currents response error', [
                'status' => $response->status(),
                'body' => substr($response->body(), 0, 200),
            ]);
            return [];
        }

        $articles = collect($response->json('news') ?? []);
        if ($articles->isEmpty()) {
            return [];
        }

        return $articles
            ->unique(fn ($item) => $item['url'] ?? md5(($item['title'] ?? '').($item['published'] ?? '')))
            ->sortByDesc('published')
            ->take($limit)
            ->map(function ($item) use ($stock) {
                $title = $item['title'] ?? 'Berita '.$stock->code;

                return [
                    'title' => $title,
                    'slug' => Str::slug($title).'-'.Str::random(4),
                    'source_name' => $item['author'] ?? 'Currents',
                    'source_url' => $item['url'] ?? null,
                    'image_url' => $item['image'] ?? null,
                    'published_at' => isset($item['published']) ? Carbon::parse($item['published']) : Carbon::now(),
                    'summary' => Str::limit(strip_tags($item['description'] ?? ''), 300),
                    'content_snippet' => Str::limit(strip_tags($item['description'] ?? ''), 500),
                    'provider' => 'currents',
                    'sentiment_label' => null,
                    'sentiment_score' => null,
                    'raw_payload' => $item,
                ];
            })
            ->values()
            ->all();
    }
}
