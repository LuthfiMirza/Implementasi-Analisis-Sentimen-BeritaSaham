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

        $queries = $this->buildQueries($stock);
        $articles = collect();

        foreach ($queries as $query) {
            try {
                $response = Http::withHeaders([
                    'User-Agent' => env('GNEWS_USER_AGENT', 'SentimenaNews/1.0'),
                ])->timeout($timeout)->get($baseUrl, [
                    'q' => $query,
                    'lang' => $lang,
                    'country' => $country,
                    'token' => $apiKey,
                    'max' => min(max($limit, 10), 10),
                    'sortby' => 'publishedAt',
                ]);
            } catch (\Throwable $e) {
                Log::warning('GNews request failed', ['error' => $e->getMessage()]);
                continue;
            }

            if (! $response->successful()) {
                Log::warning('GNews response error', [
                    'status' => $response->status(),
                    'body' => substr($response->body(), 0, 200),
                    'query' => $query,
                ]);
                continue;
            }

            $json = $response->json();
            $queryArticles = collect($json['articles'] ?? []);
            if ($queryArticles->isEmpty()) {
                Log::info('GNews returned 0 articles', ['stock' => $stock->code, 'query' => $query]);
                continue;
            }

            $articles = $articles->merge($queryArticles);
        }

        if ($articles->isEmpty()) {
            return [];
        }

        return $articles
            ->unique(fn ($item) => $item['url'] ?? md5(($item['title'] ?? '').($item['publishedAt'] ?? '')))
            ->sortByDesc('publishedAt')
            ->take($limit)
            ->map(function ($item) use ($stock) {
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
            })->values()->all();
    }

    /** Provider plans may reject older from/to ranges; failures are logged explicitly. */
    public function fetchHistorical(Stock $stock, Carbon $from, Carbon $to, int $limit = 100): ?array
    {
        $apiKey = config('services.gnews.api_key', env('GNEWS_API_KEY'));
        $baseUrl = config('services.gnews.api_base_url', env('GNEWS_BASE_URL', 'https://gnews.io/api/v4/search'));
        $lang = config('services.gnews.language', env('GNEWS_LANGUAGE', 'id'));
        $country = config('services.gnews.country', env('GNEWS_COUNTRY', 'id'));
        $timeout = config('services.gnews.timeout', env('GNEWS_TIMEOUT', 8));

        if (! $apiKey) {
            return null;
        }

        $articles = collect();
        foreach ($this->buildQueries($stock) as $query) {
            try {
                $response = Http::withHeaders([
                    'User-Agent' => env('GNEWS_USER_AGENT', 'SentimenaNews/1.0'),
                ])->timeout($timeout)->get($baseUrl, [
                    'q' => $query,
                    'lang' => $lang,
                    'country' => $country,
                    'token' => $apiKey,
                    'from' => $from->toIso8601String(),
                    'to' => $to->toIso8601String(),
                    'max' => min(max($limit, 10), 10),
                    'sortby' => 'publishedAt',
                ]);
            } catch (\Throwable $e) {
                Log::warning('GNews historical request exception', ['error' => $e->getMessage(), 'query' => $query]);
                return null;
            }

            if (! $response->successful()) {
                Log::warning('GNews historical request failed; plan may not support requested date range', [
                    'status' => $response->status(),
                    'body' => substr($response->body(), 0, 500),
                    'query' => $query,
                    'from' => $from->toDateString(),
                    'to' => $to->toDateString(),
                ]);
                return null;
            }

            $articles = $articles->merge($response->json('articles') ?? []);
        }

        return $articles
            ->unique(fn ($item) => $item['url'] ?? md5(($item['title'] ?? '').($item['publishedAt'] ?? '')))
            ->sortByDesc('publishedAt')
            ->take($limit)
            ->map(function ($item) use ($stock) {
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
            })->values()->all();
    }

    protected function buildQueries(Stock $stock): array
    {
        $aliases = collect($this->mapper->searchAliases($stock, 5));
        $sectorTerms = collect($this->mapper->sectorKeywords($stock))->take(4);
        $primaryAlias = (string) ($aliases->first() ?? $stock->code);
        $secondaryAliases = $aliases->slice(1, 2)->values();

        $aliasGroup = $aliases->map(fn ($alias) => '"'.$alias.'"')->implode(' OR ');
        $contextGroup = $sectorTerms
            ->merge(['emiten', 'bei'])
            ->unique()
            ->map(fn ($term) => '"'.$term.'"')
            ->implode(' OR ');
        $tickerGroup = collect([
            $stock->code,
            'saham '.$stock->code,
            'emiten '.$stock->code,
        ])->unique()->map(fn ($term) => '"'.$term.'"')->implode(' OR ');

        return collect([
            '"'.$primaryAlias.'"',
            ...$secondaryAliases->map(fn ($alias) => '"'.$alias.'"')->all(),
            $contextGroup ? '"'.$primaryAlias.'" AND ('.$contextGroup.')' : null,
            $contextGroup ? '('.$aliasGroup.') AND ('.$contextGroup.')' : null,
            $aliasGroup,
            $contextGroup ? '('.$tickerGroup.') AND ('.$contextGroup.')' : null,
        ])->filter()->unique()->values()->all();
    }
}
