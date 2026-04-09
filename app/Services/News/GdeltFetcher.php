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
}
