<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use DOMDocument;
use DOMXPath;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class BusinessSiteSearchFetcher implements NewsFetcherInterface
{
    protected array $sites = [
        [
            'name' => 'Bisnis.com Search',
            'url' => 'https://search.bisnis.com/?q=%s',
            'allowed_hosts' => ['bisnis.com', 'www.bisnis.com', 'market.bisnis.com', 'search.bisnis.com'],
        ],
        [
            'name' => 'Katadata Search',
            'url' => 'https://search.katadata.co.id/search?q=%s',
            'issuer_urls' => [
                'https://katadata.co.id/tags/%s',
            ],
            'allowed_hosts' => ['katadata.co.id', 'www.katadata.co.id', 'search.katadata.co.id', 'finansial.katadata.co.id'],
        ],
        [
            'name' => 'Kontan Search',
            'url' => 'https://search.kontan.co.id/search/?q=%s',
            'fallback_urls' => [
                'https://search.kontan.co.id/?q=%s',
                'https://english.kontan.co.id/search?search=%s',
            ],
            'issuer_urls' => [
                'https://insight.kontan.co.id/tag/%s',
            ],
            'allowed_hosts' => ['kontan.co.id', 'www.kontan.co.id', 'search.kontan.co.id', 'english.kontan.co.id', 'keuangan.kontan.co.id', 'investasi.kontan.co.id'],
        ],
    ];

    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $timeout = (int) config('news.business_site_search.timeout', config('news.rss_timeout', 8));
        $userAgent = (string) config('news.business_site_search.user_agent', config('news.rss_user_agent', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        $articles = collect();
        foreach ($this->sites as $site) {
            foreach ($this->buildSiteQueries($stock) as $query) {
                foreach ($this->siteUrls($site, $query) as $siteUrl) {
                    try {
                        $response = Http::withHeaders([
                            'User-Agent' => $userAgent,
                            'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        ])->timeout($timeout)->get($siteUrl);
                    } catch (\Throwable $e) {
                        Log::warning('Business site search request failed', ['site' => $site['name'], 'url' => $siteUrl, 'error' => $e->getMessage()]);
                        continue;
                    }

                    if (! $response->successful()) {
                        continue;
                    }

                    $parsed = $this->parseSearchHtml($response->body(), $stock, $site, $siteUrl);
                    if ($parsed !== []) {
                        $articles = $articles->merge($parsed);
                        break;
                    }
                }

                if ($articles->count() >= $limit) {
                    break 2;
                }
            }
        }

        return $this->prioritizeDateCoverage($articles, $limit)
            ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
            ->values()
            ->all();
    }

    /**
     * @return array<int, string>
     */
    protected function buildSiteQueries(Stock $stock): array
    {
        $limit = $stock->code === 'BBCA' ? 5 : 3;

        return collect($this->mapper->exactSearchQueries($stock, 6))
            ->take($limit)
            ->values()
            ->all();
    }

    /**
     * @return array<int, string>
     */
    protected function siteUrls(array $site, string $query): array
    {
        $templates = array_merge([$site['url']], $site['fallback_urls'] ?? []);
        $queryUrls = collect($templates)
            ->map(fn ($template) => sprintf($template, urlencode($query)));
        $issuerUrls = collect($site['issuer_urls'] ?? [])
            ->flatMap(function ($template) use ($query) {
                return collect($this->issuerSlugsFromQuery($query))
                    ->map(fn ($slug) => sprintf($template, $slug))
                    ->all();
            });

        return $queryUrls
            ->merge($issuerUrls)
            ->unique()
            ->values()
            ->all();
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    protected function parseSearchHtml(string $html, Stock $stock, array $site, string $siteUrl): array
    {
        libxml_use_internal_errors(true);
        $document = new DOMDocument();
        if (! @$document->loadHTML($html)) {
            libxml_clear_errors();
            return [];
        }
        libxml_clear_errors();

        $xpath = new DOMXPath($document);
        $results = collect();
        foreach ($this->candidateNodes($xpath) as $node) {
            $article = $this->articleFromNode($node, $siteUrl, $stock, $site);
            if ($article !== null) {
                $results->push($article);
            }
        }

        return $results->take(5)->values()->all();
    }

    /**
     * @return array<int, \DOMNode>
     */
    protected function candidateNodes(DOMXPath $xpath): array
    {
        $queries = [
            '//*[self::article or self::li or self::div][contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "result")]',
            '//*[self::article or self::li or self::div][contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "search")]',
            '//*[self::article or self::li or self::div][contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "topic")]',
            '//*[self::article or self::li or self::div][contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "card")]',
            '//article',
            '//li[a[@href]]',
            '//div[a[@href]]',
        ];

        $results = collect();
        foreach ($queries as $query) {
            $nodes = $xpath->query($query);
            if (! $nodes) {
                continue;
            }
            foreach ($nodes as $node) {
                $results->push($node);
            }
        }

        return $results
            ->unique(fn ($node) => spl_object_hash($node))
            ->values()
            ->all();
    }

    protected function articleFromNode(\DOMNode $node, string $siteUrl, Stock $stock, array $site): ?array
    {
        $anchors = [];
        if ($node instanceof \DOMElement) {
            foreach ($node->getElementsByTagName('a') as $anchor) {
                $anchors[] = $anchor;
            }
        }

        foreach ($anchors as $anchor) {
            $title = $this->normalizeSpace($anchor->textContent ?? '');
            $href = trim((string) $anchor->getAttribute('href'));
            if ($title === '' || mb_strlen($title) < 18 || $href === '') {
                continue;
            }

            $absoluteUrl = $this->absoluteUrl($siteUrl, $href);
            if (! $this->hostAllowed($absoluteUrl, $site['allowed_hosts'] ?? [])) {
                continue;
            }
            if ($this->looksLikeSearchUrl($absoluteUrl)) {
                continue;
            }

            $summary = $this->extractSummaryFromNode($node, $title);
            $combinedText = trim($title.' '.$summary);
            if (count($this->mapper->directHits($stock, $combinedText)) === 0) {
                continue;
            }

            $publishedAt = $this->extractPublishedAt($summary);

            return [
                'provider' => 'business_site_search',
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => $site['name'],
                'source_url' => $absoluteUrl,
                'published_at' => $publishedAt ?? Carbon::now(),
                'summary' => $summary ?: null,
                'content_snippet' => $summary ?: null,
                'sentiment_label' => null,
                'sentiment_score' => null,
                'raw_payload' => [
                    'search_url' => $siteUrl,
                    'site' => $site['name'],
                    'title' => $title,
                    'summary' => $summary,
                    'url' => $absoluteUrl,
                ],
            ];
        }

        return null;
    }

    protected function extractSummaryFromNode(\DOMNode $node, string $title): string
    {
        $summaryParts = [];
        if ($node instanceof \DOMElement) {
            foreach (['p', 'span', 'time', 'small', 'div'] as $tag) {
                foreach ($node->getElementsByTagName($tag) as $child) {
                    $text = $this->normalizeSpace($child->textContent ?? '');
                    if ($text === '' || $text === $title) {
                        continue;
                    }
                    $summaryParts[] = $text;
                }
            }
        }

        $summary = $this->normalizeSpace(implode(' ', array_unique($summaryParts)));
        $summary = trim(str_replace($title, '', $summary));

        return Str::limit($summary, 300);
    }

    protected function normalizeSpace(?string $text): string
    {
        return trim((string) preg_replace('/\s+/u', ' ', html_entity_decode((string) $text)));
    }

    protected function absoluteUrl(string $baseUrl, string $href): string
    {
        if (str_starts_with($href, 'http://') || str_starts_with($href, 'https://')) {
            return $href;
        }

        $parts = parse_url($baseUrl);
        $scheme = $parts['scheme'] ?? 'https';
        $host = $parts['host'] ?? '';
        if ($host === '') {
            return $href;
        }

        if (str_starts_with($href, '//')) {
            return $scheme.':'.$href;
        }
        if (str_starts_with($href, '/')) {
            return $scheme.'://'.$host.$href;
        }

        return rtrim($scheme.'://'.$host, '/').'/'.$href;
    }

    /**
     * @param array<int, string> $allowedHosts
     */
    protected function hostAllowed(string $url, array $allowedHosts): bool
    {
        $host = strtolower((string) parse_url($url, PHP_URL_HOST));
        if ($host === '') {
            return false;
        }

        foreach ($allowedHosts as $allowedHost) {
            if ($host === $allowedHost || str_ends_with($host, '.'.$allowedHost)) {
                return true;
            }
        }

        return false;
    }

    protected function looksLikeSearchUrl(string $url): bool
    {
        $path = strtolower((string) parse_url($url, PHP_URL_PATH));
        return str_contains($path, '/search');
    }

    /**
     * @return array<int, string>
     */
    protected function issuerSlugsFromQuery(string $query): array
    {
        $normalized = Str::of($query)
            ->lower()
            ->replace(['"', "'", '.', ',', 'pt ', ' tbk', 'saham ', 'emiten '], ' ')
            ->squish()
            ->value();

        $tokens = collect(explode(' ', $normalized))
            ->filter(fn ($token) => $token !== '')
            ->values();

        $slug = Str::slug($normalized);
        $shortSlug = Str::slug($tokens->take(3)->implode(' '));

        return collect([$slug, $shortSlug])
            ->filter()
            ->unique()
            ->values()
            ->all();
    }

    protected function extractPublishedAt(string $text): ?Carbon
    {
        if (preg_match('/(\d{1,2}\s+[A-Za-z]+\s+\d{4})(?:,?\s+(\d{1,2})[.:](\d{2}))?/u', $text, $matches) === 1) {
            try {
                $dateText = $this->normalizeIndonesianDate($matches[1]);
                $timeText = isset($matches[2], $matches[3]) ? sprintf(' %02d:%02d', $matches[2], $matches[3]) : '';

                return Carbon::parse($dateText.$timeText, 'Asia/Jakarta');
            } catch (\Throwable) {
                return null;
            }
        }

        return null;
    }

    protected function normalizeIndonesianDate(string $dateText): string
    {
        return str_ireplace(
            ['Januari', 'Februari', 'Maret', 'Mei', 'Juni', 'Juli', 'Agustus', 'Oktober', 'Desember'],
            ['January', 'February', 'March', 'May', 'June', 'July', 'August', 'October', 'December'],
            $dateText
        );
    }

    protected function prioritizeDateCoverage(Collection $articles, int $limit): Collection
    {
        $sorted = $articles
            ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
            ->sortByDesc('published_at')
            ->values();

        if ($limit <= 0 || $sorted->count() <= $limit) {
            return $sorted;
        }

        $selected = collect();
        $seenDates = [];

        foreach ($sorted as $article) {
            $dateKey = optional($article['published_at'] ?? null)?->toDateString() ?? 'unknown';
            if (isset($seenDates[$dateKey])) {
                continue;
            }

            $seenDates[$dateKey] = true;
            $selected->push($article);
            if ($selected->count() >= $limit) {
                return $selected;
            }
        }

        foreach ($sorted as $article) {
            $selected->push($article);
            $selected = $selected
                ->unique(fn ($item) => $item['source_url'] ?? md5(($item['title'] ?? '').($item['published_at'] ?? '')))
                ->values();
            if ($selected->count() >= $limit) {
                break;
            }
        }

        return $selected->take($limit)->values();
    }
}
