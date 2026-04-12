<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class GNewsFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $apiKey = config('services.gnews.api_key', env('GNEWS_API_KEY'));
        $baseUrl = config('services.gnews.api_base_url', env('GNEWS_BASE_URL', 'https://gnews.io/api/v4/search'));
        $lang = config('services.gnews.language', env('GNEWS_LANGUAGE', 'id'));
        $country = config('services.gnews.country', env('GNEWS_COUNTRY', 'id'));
        $timeout = config('services.gnews.timeout', env('GNEWS_TIMEOUT', 8));

        if (! $apiKey) {
            return [];
        }

        $keywords = $this->mapper->keywords($stock);
        $query = collect($keywords)->take(3)->map(fn ($k) => '"'.$k.'"')->implode(' OR ');

        try {
            $response = Http::withHeaders([
                'User-Agent' => env('GNEWS_USER_AGENT', 'SentimenaNews/1.0'),
            ])->timeout($timeout)->get($baseUrl, [
                'q' => $query,
                'lang' => $lang,
                'country' => $country,
                'token' => $apiKey,
                'max' => min($limit, 10),
                'sortby' => 'publishedAt',
            ]);
        } catch (\Throwable $e) {
            Log::warning('GNews request failed', ['error' => $e->getMessage()]);
            return [];
        }

        if (! $response->successful()) {
            Log::warning('GNews response error', [
                'status' => $response->status(),
                'body' => substr($response->body(), 0, 200),
            ]);
            return [];
        }

        $json = $response->json();
        $articles = $json['articles'] ?? [];

        if (empty($articles)) {
            Log::info('GNews returned 0 articles', ['stock' => $stock->code, 'query' => $query]);
            return [];
        }

        return collect($articles)->take($limit)->map(function ($item) use ($stock) {
            $title = $item['title'] ?? 'Berita '.$stock->code;
            return [
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => data_get($item, 'source.name'),
                'source_url' => $item['url'] ?? null,
                'published_at' => isset($item['publishedAt']) ? Carbon::parse($item['publishedAt']) : Carbon::now(),
                'summary' => Str::limit(strip_tags($item['description'] ?? ''), 300),
                'content_snippet' => Str::limit(strip_tags($item['content'] ?? $item['description'] ?? ''), 500),
                'provider' => 'gnews',
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => $item,
            ];
        })->all();
    }
}
