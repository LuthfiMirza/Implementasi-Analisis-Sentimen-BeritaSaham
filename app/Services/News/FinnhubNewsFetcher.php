<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class FinnhubNewsFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $apiKey = config('services.finnhub.api_key', env('FINNHUB_API_KEY'));
        $baseUrl = config('services.finnhub.news_base_url', env('FINNHUB_BASE_URL', 'https://finnhub.io/api/v1/company-news'));

        if (! $apiKey || ! $baseUrl) {
            return [];
        }

        $symbol = $stock->code.(Str::endsWith($stock->code, '.JK') ? '' : '.JK');
        $to = Carbon::now()->toDateString();
        $from = Carbon::now()->subDays(7)->toDateString();

        $cacheKey = "finnhub-news-{$symbol}-{$from}-{$to}-{$limit}";

        return Cache::remember($cacheKey, now()->addMinutes(5), function () use ($baseUrl, $apiKey, $symbol, $from, $to, $limit, $stock) {
            $response = Http::get($baseUrl, [
                'symbol' => $symbol,
                'from' => $from,
                'to' => $to,
                'token' => $apiKey,
            ]);

            if (! $response->successful()) {
                Log::warning('Finnhub news request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
                return [];
            }

            $articles = $response->json();
            if (! is_array($articles)) {
                return [];
            }

            return collect($articles)
                ->sortByDesc('datetime')
                ->take($limit)
                ->map(function ($item) use ($stock) {
                    $title = $item['headline'] ?? 'Berita '.$stock->code;
                    $slug = Str::slug($title).'-'.Str::random(4);

                    return [
                        'title' => $title,
                        'slug' => $slug,
                        'source_name' => $item['source'] ?? 'Finnhub',
                        'source_url' => $item['url'] ?? null,
                        'published_at' => isset($item['datetime']) ? Carbon::createFromTimestamp($item['datetime']) : Carbon::now(),
                        'summary' => $item['summary'] ?? null,
                        'content_snippet' => $item['summary'] ?? null,
                        'sentiment_label' => null,
                        'sentiment_score' => null,
                        'raw_payload' => $item,
                    ];
                })
                ->all();
        });
    }
}
