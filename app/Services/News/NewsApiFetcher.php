<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class NewsApiFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $baseUrl = config('services.news.api_base_url', env('NEWS_API_BASE_URL'));
        $apiKey = config('services.news.api_key', env('NEWS_API_KEY'));
        $language = config('services.news.language', env('NEWS_API_LANGUAGE', 'id'));
        $timeout = config('services.news.timeout', env('NEWS_API_TIMEOUT', 8));
        $userAgent = config('services.news.user_agent', env('NEWS_API_USER_AGENT', 'SentimenaNews/1.0'));

        if (! $baseUrl || ! $apiKey) {
            return [];
        }

        $query = $this->mapper->contextualQuery($stock);
        $paramsBase = [
            'q' => $query,
            'searchIn' => 'title,description,content',
            'sortBy' => 'publishedAt',
            'pageSize' => $limit,
        ];

        $attempts = [
            array_filter([...$paramsBase, 'language' => $language]),
            array_filter([...$paramsBase, 'language' => 'en']),
            $paramsBase,
        ];

        $articles = [];
        foreach ($attempts as $params) {
            try {
                $response = Http::withHeaders([
                    'X-Api-Key' => $apiKey,
                    'User-Agent' => $userAgent,
                    'Accept' => 'application/json',
                ])->timeout($timeout)->get($baseUrl, $params);
            } catch (\Throwable $e) {
                Log::warning('NewsAPI request exception', ['error' => $e->getMessage(), 'params' => $params]);
                continue;
            }

            if (! $response->successful()) {
                Log::warning('NewsAPI request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                    'params' => $params,
                ]);
                continue;
            }

            $json = $response->json();
            if (! is_array($json) || ! isset($json['articles']) || ! is_array($json['articles'])) {
                Log::warning('NewsAPI invalid payload', ['payload' => $json]);
                continue;
            }

            $articles = $json['articles'];
            if (count($articles)) {
                break;
            }
        }

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
                'provider' => 'newsapi',
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => $item,
            ];
        })->all();
    }
}
