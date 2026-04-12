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
        $baseUrl = config('services.gnews.api_base_url', env('GNEWS_BASE_URL'));
        $apiKey = config('services.gnews.api_key', env('GNEWS_API_KEY'));
        $language = config('services.gnews.language', env('GNEWS_LANGUAGE', 'id'));
        $country = config('services.gnews.country', env('GNEWS_COUNTRY', 'id'));
        $timeout = config('services.gnews.timeout', env('GNEWS_TIMEOUT', 8));
        $userAgent = config('services.gnews.user_agent', env('GNEWS_USER_AGENT', 'SentimenaNews/1.0'));

        if (! $baseUrl || ! $apiKey) {
            return [];
        }

        $query = $this->mapper->contextualQuery($stock);
        $params = [
            'q' => $query,
            'lang' => $language,
            'country' => $country,
            'max' => $limit,
            'token' => $apiKey,
        ];

        try {
            $response = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'application/json',
            ])->timeout($timeout)->get($baseUrl, $params);
        } catch (\Throwable $e) {
            Log::warning('GNews request exception', ['error' => $e->getMessage(), 'params' => $params]);
            return [];
        }

        if (! $response->successful()) {
            Log::warning('GNews request failed', [
                'status' => $response->status(),
                'body' => $response->body(),
                'params' => $params,
            ]);
            return [];
        }

        $json = $response->json();
        if (! is_array($json) || ! isset($json['articles']) || ! is_array($json['articles'])) {
            Log::warning('GNews invalid payload', ['payload' => $json]);
            return [];
        }

        $articles = $json['articles'];
        if (! $articles) {
            return [];
        }

        return collect($articles)->take($limit)->map(function ($item) use ($stock) {
            $title = $item['title'] ?? 'Berita '.$stock->code;
            $slug = Str::slug($title).'-'.Str::random(4);

            return [
                'title' => $title,
                'slug' => $slug,
                'source_name' => data_get($item, 'source.name'),
                'source_url' => $item['url'] ?? null,
                'published_at' => $item['publishedAt'] ? Carbon::parse($item['publishedAt']) : Carbon::now(),
                'summary' => $item['description'] ?? null,
                'content_snippet' => $item['content'] ?? null,
                'provider' => 'gnews',
                'language' => $item['language'] ?? 'id',
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => $item,
            ];
        })->all();
    }
}
