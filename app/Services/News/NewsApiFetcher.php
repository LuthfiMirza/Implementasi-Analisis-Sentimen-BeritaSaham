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

        if (! $baseUrl || ! $apiKey) {
            return [];
        }

        $query = $this->mapper->queryString($stock);
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
            $response = Http::withHeaders([
                'X-Api-Key' => $apiKey,
            ])->get($baseUrl, $params);

            if (! $response->successful()) {
                Log::warning('NewsAPI request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                    'params' => $params,
                ]);
                continue;
            }

            $articles = $response->json('articles', []);
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
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => $item,
            ];
        })->all();
    }
}
