<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ApiNewsFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $baseUrl = config('services.news.api_base_url', env('NEWS_API_BASE_URL'));
        $apiKey = config('services.news.api_key', env('NEWS_API_KEY'));
        $language = config('services.news.language', env('NEWS_API_LANGUAGE', 'id'));

        if (! $baseUrl || ! $apiKey) {
            Log::info('ApiNewsFetcher missing baseUrl/apiKey', ['baseUrl' => $baseUrl ? 'set' : 'null', 'apiKey' => $apiKey ? 'set' : 'null']);
            return [];
        }

        // Contoh endpoint kompatibel dengan NewsAPI (v2/everything). Sesuaikan query sesuai provider Anda.
        $query = $stock->code.' OR "'.$stock->company_name.'"';
        $baseParams = [
            'q' => $query,
            'searchIn' => 'title,description,content',
            'sortBy' => 'publishedAt',
            'pageSize' => $limit,
        ];

        // Coba dengan filter bahasa (ID) dulu, lalu fallback tanpa filter jika kosong.
        $attempts = [
            array_filter([...$baseParams, 'language' => $language]),
            $baseParams,
        ];

        $articles = [];

        foreach ($attempts as $index => $params) {
            $response = Http::withHeaders([
                'X-Api-Key' => $apiKey,
            ])->get($baseUrl, $params);

            if (! $response->successful()) {
                Log::warning('News API request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                    'params' => $params,
                ]);
                continue;
            }

            $articles = $response->json('articles', []);
            $totalResults = $response->json('totalResults', 0);

            if ($totalResults > 0 && ! empty($articles)) {
                break;
            }

            Log::info('News API returned no articles', [
                'stock' => $stock->code,
                'query' => $params['q'] ?? null,
                'language' => $params['language'] ?? null,
                'attempt' => $index + 1,
            ]);
        }

        if (empty($articles)) {
            return [];
        }

        return collect($articles)
            ->take($limit)
            ->map(function ($item) use ($stock) {
                $title = $item['title'] ?? 'Berita '.$stock->code;
                $slug = Str::slug($title).'-'.Str::random(4);

                return [
                    'provider' => 'api',
                    'title' => $title,
                    'slug' => $slug,
                    'source_name' => data_get($item, 'source.name'),
                    'source_url' => $item['url'] ?? null,
                    'published_at' => $item['publishedAt'] ? Carbon::parse($item['publishedAt']) : Carbon::now(),
                    'summary' => $item['description'] ?? null,
                    'content_snippet' => $item['content'] ?? null,
                    'sentiment_label' => null, // akan dianalisis di NewsAggregationService jika tidak ada
                    'sentiment_score' => null,
                    'raw_payload' => $item,
                ];
            })
            ->all();
    }
}
