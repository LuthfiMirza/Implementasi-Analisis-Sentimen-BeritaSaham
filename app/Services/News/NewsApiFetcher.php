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

        $queries = $this->buildQueries($stock);
        $paramsBase = [
            'searchIn' => 'title,description,content',
            'sortBy' => 'publishedAt',
            'pageSize' => $limit,
            'language' => $language,
        ];

        $articles = [];
        $attemptIndex = 0;
        foreach ($queries as $q) {
            $attemptIndex++;
            $params = array_merge($paramsBase, ['q' => $q, 'language' => 'id']);
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
                Log::warning('NewsAPI invalid payload', ['payload' => $json, 'params' => $params]);
                continue;
            }

            $articles = $json['articles'];
            if (count($articles)) {
                break;
            }

            Log::info('NewsAPI returned empty articles', [
                'stock' => $stock->code,
                'query' => $params['q'] ?? null,
                'language' => $params['language'] ?? null,
                'attempt' => $attemptIndex,
                'status' => $json['status'] ?? null,
                'totalResults' => $json['totalResults'] ?? null,
            ]);
        }

        if (! $articles) {
            return [];
        }

        $blacklistDomains = [
            'globenewswire.com', 'prnewswire.com', 'businesswire.com',
            'accesswire.com', 'einpresswire.com', 'markets.businessinsider.com',
            'finance.yahoo.com',
        ];

        $preferredDomains = [
            'cnbcindonesia.com', 'kontan.co.id', 'bisnis.com',
            'detik.com', 'kompas.com', 'idx.co.id', 'investor.id', 'katadata.co.id',
        ];

        $articles = collect($articles)
            ->filter(function ($item) use ($blacklistDomains) {
                $domain = strtolower(parse_url($item['url'] ?? '', PHP_URL_HOST) ?? '');
                foreach ($blacklistDomains as $bl) {
                    if (str_contains($domain, $bl)) {
                        return false;
                    }
                }
                return true;
            })
            ->sortByDesc(function ($item) use ($preferredDomains) {
                $domain = strtolower(parse_url($item['url'] ?? '', PHP_URL_HOST) ?? '');
                foreach ($preferredDomains as $i => $pd) {
                    if (str_contains($domain, $pd)) {
                        return 100 - $i;
                    }
                }
                return 0;
            })
            ->take($limit);

        return $articles->map(function ($item) use ($stock) {
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

    /**
     * Bangun query pendek untuk NewsAPI agar tidak memicu queryTooLong.
     * - Prioritas: alias utama (kode + nama pendek) + subset konteks.
     * - Truncation jika masih > 480 chars.
     */
    protected function buildQueries(Stock $stock): array
    {
        $aliasOnly = $this->mapper->queryString($stock);
        $ctxShort = array_slice(config('news.context_keywords', []), 0, 5);
        $queryCtx = $this->mapper->contextualQuery($stock, $ctxShort);

        $candidates = array_values(array_filter([$aliasOnly, $queryCtx]));

        return collect($candidates)->map(function ($q) {
            $max = 480;
            if (strlen($q) <= $max) {
                return $q;
            }
            // Potong query OR menjadi segmen pendek
            $parts = preg_split('/\s+OR\s+/i', $q);
            $trimmed = [];
            $length = 0;
            foreach ($parts as $part) {
                $part = trim($part);
                if ($part === '') {
                    continue;
                }
                $candidateLen = ($length === 0 ? strlen($part) : $length + 4 + strlen($part)); // 4 for ' OR '
                if ($candidateLen > $max) {
                    break;
                }
                $trimmed[] = $part;
                $length = $candidateLen;
            }
            $short = implode(' OR ', $trimmed);
            Log::info('NewsAPI query truncated', ['original_len' => strlen($q), 'final_len' => strlen($short)]);
            return $short;
        })->unique()->values()->all();
    }
}
