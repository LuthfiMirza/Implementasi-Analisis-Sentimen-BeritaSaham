<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class GdeltFetcher implements NewsFetcherInterface
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $baseUrl = env('GDELT_BASE_URL', 'https://api.gdeltproject.org/api/v2/doc/doc');
        $query = $this->mapper->queryString($stock);
        $params = [
            'query' => $query.' AND (sourcelang:indonesia OR sourcelang:english)',
            'maxrecords' => $limit,
            'format' => 'json',
        ];

        $response = Http::get($baseUrl, $params);
        if (! $response->successful()) {
            Log::warning('GDELT request failed', [
                'status' => $response->status(),
                'body' => $response->body(),
            ]);
            return [];
        }

        $articles = data_get($response->json(), 'articles', []);
        if (! is_array($articles)) {
            return [];
        }

        return collect($articles)
            ->take($limit)
            ->map(function ($item) use ($stock) {
                $title = $item['title'] ?? 'Berita '.$stock->code;
                $slug = Str::slug($title).'-'.Str::random(4);

                return [
                    'title' => $title,
                    'slug' => $slug,
                    'source_name' => $item['sourceCommonName'] ?? 'GDELT',
                    'source_url' => $item['url'] ?? null,
                    'published_at' => isset($item['seendate']) ? Carbon::parse($item['seendate']) : Carbon::now(),
                    'summary' => $item['excerpt'] ?? null,
                    'content_snippet' => $item['snippet'] ?? null,
                    'sentiment_label' => null,
                    'sentiment_score' => null,
                    'raw_payload' => $item,
                ];
            })
            ->all();
    }

    public function fetchHistorical(string $query, Carbon $from, Carbon $to, int $maxRecords = 250): array
    {
        $baseUrl = env('GDELT_BASE_URL', 'https://api.gdeltproject.org/api/v2/doc/doc');
        try {
            $response = Http::timeout((int) config('news.gdelt.timeout', 20))->get($baseUrl, [
                'query' => $query.' AND (sourcelang:indonesia OR sourcelang:english)',
                'startdatetime' => $from->copy()->utc()->format('YmdHis'),
                'enddatetime' => $to->copy()->utc()->format('YmdHis'),
                'maxrecords' => min($maxRecords, 250),
                'format' => 'json',
                'sort' => 'datedesc',
            ]);
        } catch (\Throwable $e) {
            Log::warning('GDELT historical request exception', [
                'error' => $e->getMessage(),
                'from' => $from->toDateTimeString(),
                'to' => $to->toDateTimeString(),
            ]);

            return [];
        }

        if (! $response->successful()) {
            Log::warning('GDELT historical request failed', [
                'status' => $response->status(),
                'body' => $response->body(),
                'from' => $from->toDateTimeString(),
                'to' => $to->toDateTimeString(),
            ]);
            return [];
        }

        $articles = data_get($response->json(), 'articles', []);
        if (! is_array($articles)) {
            return [];
        }

        return collect($articles)->map(function ($item) {
            $title = $item['title'] ?? 'Berita historis GDELT';

            return [
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => $item['sourceCommonName'] ?? 'GDELT',
                'source_url' => $item['url'] ?? null,
                'published_at' => isset($item['seendate']) ? Carbon::parse($item['seendate']) : Carbon::now(),
                'summary' => $item['excerpt'] ?? null,
                'content_snippet' => $item['snippet'] ?? null,
                'provider' => 'gdelt',
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => $item,
            ];
        })->all();
    }
}
