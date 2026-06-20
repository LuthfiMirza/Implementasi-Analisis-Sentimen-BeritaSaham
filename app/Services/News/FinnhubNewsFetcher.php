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
        $to = Carbon::now();
        $from = Carbon::now()->subDays(7);

        return collect($this->fetchHistorical($symbol, $from, $to, $limit))
            ->take($limit)
            ->all();
    }

    public function fetchHistorical(string $symbol, Carbon $from, Carbon $to, int $limit = 100): ?array
    {
        $apiKey = config('services.finnhub.api_key', env('FINNHUB_API_KEY'));
        $baseUrl = config('services.finnhub.news_base_url', env('FINNHUB_BASE_URL', 'https://finnhub.io/api/v1/company-news'));

        if (! $apiKey || ! $baseUrl) {
            return null;
        }

        $symbol = Str::endsWith($symbol, '.JK') ? $symbol : $symbol.'.JK';
        $stockCode = Str::before($symbol, '.JK');
        $allArticles = collect();

        foreach ($this->monthlyChunks($from, $to) as [$chunkFrom, $chunkTo]) {
            $fromString = $chunkFrom->toDateString();
            $toString = $chunkTo->toDateString();

            $cacheKey = "finnhub-news-{$symbol}-{$fromString}-{$toString}-{$limit}";

            $articles = Cache::remember($cacheKey, now()->addMinutes(5), function () use ($baseUrl, $apiKey, $symbol, $fromString, $toString) {
                try {
                    $response = Http::get($baseUrl, [
                        'symbol' => $symbol,
                        'from' => $fromString,
                        'to' => $toString,
                        'token' => $apiKey,
                    ]);
                } catch (\Throwable $e) {
                    Log::warning('Finnhub news request exception', [
                        'error' => $e->getMessage(),
                    ]);

                    return null;
                }

                if (! $response->successful()) {
                    Log::warning('Finnhub news request failed', [
                        'status' => $response->status(),
                        'body' => $response->body(),
                    ]);

                    return null;
                }

                $articles = $response->json();
                if (! is_array($articles)) {
                    return [];
                }

                return $articles;
            });

            if ($articles === null) {
                Cache::forget($cacheKey);

                Log::warning('Finnhub historical chunk failed; will retry on next run', [
                    'symbol' => $symbol,
                    'from' => $fromString,
                    'to' => $toString,
                ]);

                return null;
            }

            $allArticles = $allArticles->merge($articles);
        }

        return $allArticles
            ->sortByDesc('datetime')
            ->take($limit)
            ->map(function ($item) use ($stockCode) {
                $title = $item['headline'] ?? 'Berita '.$stockCode;
                $slug = Str::slug($title).'-'.Str::random(4);

                return [
                    'provider' => 'finnhub',
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
    }

    protected function monthlyChunks(Carbon $from, Carbon $to): array
    {
        $chunks = [];
        $cursor = $from->copy()->startOfDay();
        $end = $to->copy()->endOfDay();

        while ($cursor->lte($end)) {
            $chunkEnd = $cursor->copy()->endOfMonth()->min($end);
            $chunks[] = [$cursor->copy(), $chunkEnd->copy()];
            $cursor = $chunkEnd->copy()->addDay()->startOfDay();
        }

        return $chunks;
    }
}
