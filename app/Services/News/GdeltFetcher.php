<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class GdeltFetcher implements NewsFetcherInterface
{
    /** Timestamp (microtime float) of the last request sent, shared across instances within this process. */
    protected static ?float $lastRequestAt = null;

    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper) {}

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $baseUrl = env('GDELT_BASE_URL', 'https://api.gdeltproject.org/api/v2/doc/doc');
        $query = $this->mapper->queryString($stock);
        $params = [
            'query' => self::wrapQuery($query).' AND (sourcelang:indonesia OR sourcelang:english)',
            'maxrecords' => $limit,
            'format' => 'json',
        ];

        self::throttle();

        // Laravel's HTTP client defaults connectTimeout to 10s independently of ->timeout() --
        // live-verified this was silently truncating every request to GDELT (which sometimes takes
        // >10s just to establish the connection) at exactly 10.0s regardless of the 20s ->timeout()
        // already set below. Must set both explicitly.
        try {
            $response = Http::connectTimeout((int) config('news.gdelt.connect_timeout', 20))
                ->timeout((int) config('news.gdelt.timeout', 20))
                ->get($baseUrl, $params);
        } catch (\Throwable $e) {
            Log::warning('GDELT request exception', ['error' => $e->getMessage()]);

            return [];
        }

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

    public function fetchHistorical(string $query, Carbon $from, Carbon $to, int $maxRecords = 250): ?array
    {
        $baseUrl = env('GDELT_BASE_URL', 'https://api.gdeltproject.org/api/v2/doc/doc');
        self::throttle();
        try {
            // See fetchForStock() for why connectTimeout must be set explicitly alongside timeout().
            $response = Http::connectTimeout((int) config('news.gdelt.connect_timeout', 20))
                ->timeout((int) config('news.gdelt.timeout', 20))
                ->get($baseUrl, [
                    'query' => self::wrapQuery($query).' AND (sourcelang:indonesia OR sourcelang:english)',
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

            return null;
        }

        if (! $response->successful()) {
            Log::warning('GDELT historical request failed', [
                'status' => $response->status(),
                'body' => $response->body(),
                'from' => $from->toDateTimeString(),
                'to' => $to->toDateTimeString(),
            ]);

            return null;
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

    /**
     * GDELT's query parser rejects a bare "A OR B OR C" chain once it's followed by
     * " AND (...)" -- "Boolean OR's may only appear inside of a () clause." StockKeywordMapper
     * builds exactly that kind of OR chain, so it must be parenthesized before being combined
     * with the language filter. Wrapping an already-parenthesized/single-term query is harmless.
     */
    /**
     * GDELT's free-tier docs endpoint enforces "one request every 5 seconds" (429 otherwise).
     * A single news:fetch run iterates every active stock in one PHP process, so without this
     * throttle every stock after the first gets rate-limited and silently returns []. Confirmed
     * live: a 12-stock run produced 429s for every gdelt call after the first. Skipped in tests
     * (Http::fake has no real network delay to respect).
     */
    protected static function throttle(): void
    {
        if (app()->runningUnitTests()) {
            return;
        }

        $minGapSeconds = 5.5;
        if (self::$lastRequestAt !== null) {
            $elapsed = microtime(true) - self::$lastRequestAt;
            if ($elapsed < $minGapSeconds) {
                usleep((int) (($minGapSeconds - $elapsed) * 1_000_000));
            }
        }
        self::$lastRequestAt = microtime(true);
    }

    protected static function wrapQuery(string $query): string
    {
        $query = self::dropShortPhrases($query);
        if ($query === '' || (str_starts_with($query, '(') && str_ends_with($query, ')'))) {
            return $query;
        }

        return '('.$query.')';
    }

    /**
     * GDELT also rejects quoted phrases under 5 characters ("The specified phrase is too
     * short", confirmed live against api.gdeltproject.org -- a bare 4-char "BBCA" was still
     * rejected). StockKeywordMapper includes short ticker-only terms like "BCA"/"BBCA" that
     * trip this. Drop them and rejoin the remaining OR-chain rather than failing the whole query.
     */
    protected static function dropShortPhrases(string $query): string
    {
        $query = trim($query);
        if (! preg_match_all('/"([^"]*)"/', $query, $matches)) {
            return $query;
        }

        $kept = array_values(array_filter($matches[1], fn ($phrase) => mb_strlen(trim($phrase)) >= 5));
        if ($kept === $matches[1]) {
            return $query;
        }

        return implode(' OR ', array_map(fn ($phrase) => '"'.$phrase.'"', $kept));
    }
}
