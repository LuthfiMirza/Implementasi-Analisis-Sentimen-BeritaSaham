<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class OjkRssFetcher implements NewsFetcherInterface
{
    /**
     * Official OJK Pasar Modal feeds.
     *
     * @var array<string, string>
     */
    public const FEEDS = [
        'ojk_siaran_pers' => 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/rss',
        'ojk_pasar_modal' => 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/rss',
    ];

    public const HTML_FALLBACK_PAGES = [
        'ojk_pasar_modal_page' => 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers',
        'ojk_press_page' => 'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers',
        'ojk_pasar_modal_default' => 'https://www.ojk.go.id/id/kanal/pasar-modal/berita-dan-kegiatan/siaran-pers/Default.aspx',
        'ojk_press_default' => 'https://www.ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Default.aspx',
    ];

    public const MARKET_KEYWORDS = [
        'saham', 'emiten', 'bursa', 'pasar modal', 'efek', 'investasi',
        'sekuritas', 'listing', 'ipo', 'rights issue', 'dividen',
        'laporan keuangan', 'keterbukaan', 'aksi korporasi',
        'merger', 'akuisisi', 'obligasi', 'sukuk', 'reksa dana',
        'ihsg', 'bei', 'idx', 'suku bunga', 'inflasi', 'kebijakan',
        'peraturan', 'regulasi', 'sanksi', 'izin', 'pencabutan',
    ];

    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        // OJK feed bersifat makro, sehingga hasilnya sengaja tidak issuer-specific.
        return $this->fetchForMarket($limit);
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    public function fetchForMarketInRange(
        CarbonInterface|string $from,
        CarbonInterface|string $to,
        int $limit = 100,
        ?int $candidateLimit = null
    ): array {
        return $this->fetchForMarket($limit, $from, $to, $candidateLimit);
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    public function fetchForMarket(
        int $limit = 10,
        CarbonInterface|string|null $from = null,
        CarbonInterface|string|null $to = null,
        ?int $candidateLimit = null
    ): array
    {
        $timeout = config('news.rss_timeout', env('NEWS_RSS_TIMEOUT', 8));
        $userAgent = config('news.rss_user_agent', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'));
        $sourceWeight = (float) config('news.source_weights.ojk_rss', 1.0);
        [$fromDate, $toDate] = $this->resolveWindow($from, $to);
        $windowPayload = $this->windowPayload($fromDate, $toDate);
        $articles = collect();

        foreach (collect(self::FEEDS)->unique()->all() as $feedName => $url) {
            try {
                $response = Http::withHeaders([
                    'User-Agent' => $userAgent,
                    'Accept' => 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1',
                ])->timeout($timeout)->get($url);
            } catch (\Throwable $e) {
                Log::error('OJK RSS request failed', ['feed' => $feedName, 'url' => $url, 'error' => $e->getMessage()]);
                continue;
            }

            if (! $response->successful()) {
                Log::warning('OJK RSS fetch failed', ['feed' => $feedName, 'url' => $url, 'status' => $response->status()]);
                continue;
            }

            $body = trim($response->body());
            if ($body === '') {
                Log::warning('OJK RSS empty body', ['feed' => $feedName, 'url' => $url]);
                continue;
            }

            $contentType = strtolower($response->header('Content-Type') ?? '');
            if (str_contains($contentType, 'html') || stripos($body, '<html') !== false) {
                Log::warning('OJK RSS returned HTML, skipped', ['feed' => $feedName, 'url' => $url]);
                continue;
            }

            foreach ($this->parseFeedItems($body, $url) as $item) {
                $title = trim((string) ($item['title'] ?? ''));
                $description = trim(strip_tags((string) ($item['description'] ?? '')));
                $link = trim((string) ($item['link'] ?? ''));
                $pubDate = trim((string) ($item['pubDate'] ?? ''));

                if ($title === '' || $link === '') {
                    continue;
                }

                $matchedKeywords = $this->marketKeywordHits($title.' '.$description);
                if (! count($matchedKeywords)) {
                    continue;
                }

                $publishedAt = $this->parsePublishedAt($pubDate);
                if (! $this->shouldKeepPublishedAt($publishedAt, $fromDate, $toDate)) {
                    continue;
                }
                $score = $this->qualityScore($matchedKeywords, $sourceWeight);
                $qualityBand = $this->qualityBand($score['final_quality_score']);
                $relevanceBand = $score['relevance_score'] >= (float) config('news.high_threshold', 0.55)
                    ? 'high'
                    : 'medium';

                $articles->push([
                    'title' => $title,
                    'slug' => Str::slug($title).'-'.Str::random(4),
                    'source_name' => 'OJK Pasar Modal',
                    'source_url' => $link,
                    'published_at' => $publishedAt,
                    'summary' => Str::limit($description, 500),
                    'content_snippet' => Str::limit($description, 500),
                    'full_text' => $description,
                    'provider' => 'ojk_rss',
                    'language' => 'id',
                    'detected_language' => 'id',
                    'relevance_score' => $score['relevance_score'],
                    'relevance_band' => $relevanceBand,
                    'entity_match_score' => $score['entity_match_score'],
                    'market_context_score' => $score['market_context_score'],
                    'language_score' => 1.0,
                    'final_quality_score' => $score['final_quality_score'],
                    'quality_band' => $qualityBand,
                    'source_weight' => $sourceWeight,
                    'matched_keywords' => $matchedKeywords,
                    'quality_flags' => ['macro_regulatory', 'ojk_official'],
                    'issuer_specificity' => 'macro_regulatory',
                    'skip_relevance_rescore' => true,
                    'raw_payload' => [
                        'feed' => $feedName,
                        'feed_url' => $url,
                        'macro_scope' => 'all_stocks',
                        'matched_market_keywords' => $matchedKeywords,
                        'source_type' => 'official_regulator',
                        'fetch_window' => $windowPayload,
                    ],
                ]);
            }
        }

        $shouldFetchHtmlFallback = $fromDate !== null
            || $toDate !== null
            || $articles->count() < $limit;

        if ($shouldFetchHtmlFallback) {
            $articles = $articles->merge(
                $this->fetchFromHtmlFallback($limit, $timeout, $userAgent, $sourceWeight, $fromDate, $toDate, $candidateLimit)
            );
        }

        return $articles
            ->sortByDesc('published_at')
            ->unique(fn ($article) => $article['source_url'] ?? md5(($article['title'] ?? '').($article['published_at'] ?? '')))
            ->take($limit)
            ->values()
            ->all();
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    protected function fetchFromHtmlFallback(
        int $limit,
        int $timeout,
        string $userAgent,
        float $sourceWeight,
        ?CarbonInterface $fromDate = null,
        ?CarbonInterface $toDate = null,
        ?int $candidateLimit = null
    ): array
    {
        $articles = collect(
            $this->fetchFromPaginatedListing(
                $limit,
                $timeout,
                $userAgent,
                $sourceWeight,
                $fromDate,
                $toDate,
                $candidateLimit
            )
        );

        if (($fromDate || $toDate) && $articles->isNotEmpty()) {
            return $articles
                ->sortByDesc('published_at')
                ->unique(fn ($article) => $article['source_url'] ?? md5(($article['title'] ?? '').($article['published_at'] ?? '')))
                ->take($limit)
                ->values()
                ->all();
        }

        $candidates = collect();
        $windowPayload = $this->windowPayload($fromDate, $toDate);
        $skipGenericPages = [
            'ojk_press_page',
            'ojk_press_default',
        ];

        foreach (collect(self::HTML_FALLBACK_PAGES)->unique()->all() as $pageName => $url) {
            if (in_array($pageName, $skipGenericPages, true)) {
                continue;
            }

            try {
                $response = Http::withHeaders([
                    'User-Agent' => $userAgent,
                    'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                ])->timeout(max($timeout, 12))->get($url);
            } catch (\Throwable $e) {
                Log::warning('OJK HTML fallback request failed', ['page' => $pageName, 'url' => $url, 'error' => $e->getMessage()]);
                continue;
            }

            if (! $response->successful()) {
                Log::warning('OJK HTML fallback fetch failed', ['page' => $pageName, 'url' => $url, 'status' => $response->status()]);
                continue;
            }

            $candidates = $candidates->merge($this->parseHtmlListing($response->body(), $url));
        }

        if ($candidates->isEmpty()) {
            return $articles
                ->sortByDesc('published_at')
                ->unique(fn ($article) => $article['source_url'] ?? md5(($article['title'] ?? '').($article['published_at'] ?? '')))
                ->take($limit)
                ->values()
                ->all();
        }

        $candidateLimit ??= $fromDate || $toDate
            ? (int) config('news.ojk_backfill_candidate_limit', 200)
            : max(min($limit * 2, 12), 6);
        $prioritizedCandidates = $candidates
            ->unique('source_url')
            ->sortByDesc(function ($candidate) {
                return count($this->marketKeywordHits(
                    ($candidate['title'] ?? '').' '.($candidate['source_url'] ?? '')
                ));
            })
            ->values()
            ->take($candidateLimit);

        foreach ($prioritizedCandidates as $candidate) {
            $detail = $this->hydrateHtmlCandidate($candidate, $timeout, $userAgent);
            if (! $detail) {
                continue;
            }

            if (! $this->shouldKeepPublishedAt($detail['published_at'] ?? null, $fromDate, $toDate)) {
                continue;
            }

            $matchedKeywords = $this->marketKeywordHits(implode(' ', array_filter([
                $candidate['title'] ?? '',
                $detail['summary'] ?? '',
                $detail['full_text'] ?? '',
            ])));

            if (! count($matchedKeywords)) {
                continue;
            }

            $score = $this->qualityScore($matchedKeywords, $sourceWeight);
            $articles->push([
                'title' => $detail['title'] ?? $candidate['title'],
                'slug' => Str::slug($detail['title'] ?? $candidate['title']).'-'.Str::random(4),
                'source_name' => 'OJK Pasar Modal',
                'source_url' => $candidate['source_url'],
                'published_at' => $detail['published_at'] ?? Carbon::now('Asia/Jakarta'),
                'summary' => Str::limit($detail['summary'] ?? $candidate['title'], 500),
                'content_snippet' => Str::limit($detail['summary'] ?? $candidate['title'], 500),
                'full_text' => $detail['full_text'] ?? $candidate['title'],
                'provider' => 'ojk_rss',
                'language' => $detail['language'] ?? 'id',
                'detected_language' => $detail['language'] ?? 'id',
                'relevance_score' => $score['relevance_score'],
                'relevance_band' => $score['relevance_score'] >= (float) config('news.high_threshold', 0.55) ? 'high' : 'medium',
                'entity_match_score' => $score['entity_match_score'],
                'market_context_score' => $score['market_context_score'],
                'language_score' => ($detail['language'] ?? 'id') === 'en' ? 0.9 : 1.0,
                'final_quality_score' => $score['final_quality_score'],
                'quality_band' => $this->qualityBand($score['final_quality_score']),
                'source_weight' => $sourceWeight,
                'matched_keywords' => $matchedKeywords,
                'quality_flags' => ['macro_regulatory', 'ojk_official', 'html_fallback'],
                'issuer_specificity' => 'macro_regulatory',
                'skip_relevance_rescore' => true,
                'raw_payload' => [
                    'macro_scope' => 'all_stocks',
                    'source_type' => 'official_regulator',
                    'fallback' => 'html_listing',
                    'listing_page' => $candidate['listing_page'] ?? null,
                    'matched_market_keywords' => $matchedKeywords,
                    'fetch_window' => $windowPayload,
                ],
            ]);

            if ($articles->count() >= $limit) {
                break;
            }
        }

        return $articles
            ->sortByDesc('published_at')
            ->unique(fn ($article) => $article['source_url'] ?? md5(($article['title'] ?? '').($article['published_at'] ?? '')))
            ->take($limit)
            ->values()
            ->all();
    }

    /**
     * Crawl the official OJK press-release listing with SharePoint pagination.
     * The listing already exposes title, caption, and publication date, so we
     * can filter historical windows before hydrating detail pages.
     *
     * @return array<int, array<string, mixed>>
     */
    protected function fetchFromPaginatedListing(
        int $limit,
        int $timeout,
        string $userAgent,
        float $sourceWeight,
        ?CarbonInterface $fromDate = null,
        ?CarbonInterface $toDate = null,
        ?int $candidateLimit = null
    ): array {
        $listingUrl = self::HTML_FALLBACK_PAGES['ojk_press_page'] ?? null;
        if (! $listingUrl) {
            return [];
        }

        $candidateLimit ??= $fromDate || $toDate
            ? (int) config('news.ojk_backfill_candidate_limit', 200)
            : max($limit * 2, 10);
        $maxPages = $fromDate || $toDate
            ? (int) config('news.ojk_backfill_max_pages', 18)
            : 2;
        $windowPayload = $this->windowPayload($fromDate, $toDate);

        $html = $this->fetchHtmlDocument($listingUrl, $timeout, $userAgent);
        if (! $html) {
            return [];
        }

        $candidates = collect();

        for ($page = 1; $page <= max(1, $maxPages); $page++) {
            $parsed = $this->parsePaginatedListingPage($html, $listingUrl);
            $items = collect($parsed['items'] ?? []);
            if ($items->isEmpty()) {
                break;
            }

            $pageCandidates = $items
                ->filter(fn (array $item) => ! empty($item['source_url']) && ! empty($item['published_at']))
                ->filter(fn (array $item) => $this->shouldKeepPublishedAt($item['published_at'] ?? null, $fromDate, $toDate))
                ->map(function (array $item) {
                    $matchedKeywords = $this->marketKeywordHits(implode(' ', array_filter([
                        $item['title'] ?? '',
                        $item['summary'] ?? '',
                    ])));

                    $item['matched_keywords'] = $matchedKeywords;

                    return $item;
                })
                ->filter(fn (array $item) => count($item['matched_keywords'] ?? []) > 0)
                ->values();

            $candidates = $candidates->merge($pageCandidates);

            $oldestOnPage = $items
                ->pluck('published_at')
                ->filter(fn ($publishedAt) => $publishedAt instanceof CarbonInterface)
                ->sort()
                ->first();

            if ($candidates->count() >= $candidateLimit) {
                break;
            }

            if ($fromDate && $oldestOnPage instanceof CarbonInterface && $oldestOnPage->lt($fromDate)) {
                break;
            }

            $nextTarget = $parsed['next_target'] ?? null;
            $formInputs = $parsed['form_inputs'] ?? [];
            $nextPageUrl = $parsed['form_action'] ?? $listingUrl;
            if (! $nextTarget || $formInputs === []) {
                break;
            }

            $nextHtml = $this->postListingPage($nextPageUrl, $formInputs, $nextTarget, $timeout, $userAgent);
            if (! $nextHtml) {
                break;
            }

            $html = $nextHtml;
        }

        if ($candidates->isEmpty()) {
            return [];
        }

        $articles = collect();
        $shouldHydrateDetails = ! ($fromDate || $toDate);
        $prioritizedCandidates = $candidates
            ->unique('source_url')
            ->sortByDesc(function (array $candidate) {
                $timestamp = ($candidate['published_at'] ?? null) instanceof CarbonInterface
                    ? $candidate['published_at']->getTimestamp()
                    : 0;

                return sprintf('%010d-%02d', $timestamp, count($candidate['matched_keywords'] ?? []));
            })
            ->values()
            ->take($candidateLimit);

        foreach ($prioritizedCandidates as $candidate) {
            $detail = $shouldHydrateDetails
                ? $this->hydrateHtmlCandidate($candidate, $timeout, $userAgent)
                : null;
            $title = $detail['title'] ?? $candidate['title'] ?? null;
            $summary = $detail['summary'] ?? $candidate['summary'] ?? $title;
            $fullText = $detail['full_text'] ?? $summary;
            $publishedAt = $detail['published_at'] ?? $candidate['published_at'] ?? Carbon::now('Asia/Jakarta');

            if (! $title || ! $this->shouldKeepPublishedAt($publishedAt, $fromDate, $toDate)) {
                continue;
            }

            $matchedKeywords = $this->marketKeywordHits(implode(' ', array_filter([
                $title,
                $summary,
                $fullText,
            ])));

            if (! count($matchedKeywords)) {
                continue;
            }

            $score = $this->qualityScore($matchedKeywords, $sourceWeight);
            $articles->push([
                'title' => $title,
                'slug' => Str::slug($title).'-'.Str::random(4),
                'source_name' => 'OJK Pasar Modal',
                'source_url' => $candidate['source_url'],
                'published_at' => $publishedAt,
                'summary' => Str::limit($summary, 500),
                'content_snippet' => Str::limit($summary, 500),
                'full_text' => Str::limit($fullText, 2000),
                'provider' => 'ojk_rss',
                'language' => $detail['language'] ?? $candidate['language'] ?? 'id',
                'detected_language' => $detail['language'] ?? $candidate['language'] ?? 'id',
                'relevance_score' => $score['relevance_score'],
                'relevance_band' => $score['relevance_score'] >= (float) config('news.high_threshold', 0.55) ? 'high' : 'medium',
                'entity_match_score' => $score['entity_match_score'],
                'market_context_score' => $score['market_context_score'],
                'language_score' => (($detail['language'] ?? $candidate['language'] ?? 'id') === 'en') ? 0.9 : 1.0,
                'final_quality_score' => $score['final_quality_score'],
                'quality_band' => $this->qualityBand($score['final_quality_score']),
                'source_weight' => $sourceWeight,
                'matched_keywords' => $matchedKeywords,
                'quality_flags' => ['macro_regulatory', 'ojk_official', 'paginated_listing'],
                'issuer_specificity' => 'macro_regulatory',
                'skip_relevance_rescore' => true,
                'raw_payload' => [
                    'macro_scope' => 'all_stocks',
                    'source_type' => 'official_regulator',
                    'fallback' => 'paginated_listing',
                    'listing_page' => $candidate['listing_page'] ?? $listingUrl,
                    'raw_date_text' => $candidate['raw_date_text'] ?? null,
                    'detail_hydrated' => $shouldHydrateDetails,
                    'matched_market_keywords' => $matchedKeywords,
                    'fetch_window' => $windowPayload,
                ],
            ]);

            if ($articles->count() >= $limit) {
                break;
            }
        }

        return $articles->all();
    }

    protected function parsePublishedAt(?string $pubDate): Carbon
    {
        if (! $pubDate) {
            return Carbon::now('Asia/Jakarta');
        }

        try {
            return Carbon::parse($pubDate, 'Asia/Jakarta');
        } catch (\Throwable) {
            return Carbon::now('Asia/Jakarta');
        }
    }

    protected function isTooOld(?Carbon $publishedAt): bool
    {
        if (! $publishedAt) {
            return false;
        }

        $maxAgeDays = (int) config('news.ojk_max_age_days', 365);
        if ($maxAgeDays <= 0) {
            return false;
        }

        return $publishedAt->lt(Carbon::now('Asia/Jakarta')->subDays($maxAgeDays));
    }

    protected function shouldKeepPublishedAt(
        ?Carbon $publishedAt,
        ?CarbonInterface $fromDate = null,
        ?CarbonInterface $toDate = null
    ): bool {
        if (! $publishedAt) {
            return false;
        }

        if ($fromDate || $toDate) {
            if ($fromDate && $publishedAt->lt($fromDate)) {
                return false;
            }

            if ($toDate && $publishedAt->gt($toDate)) {
                return false;
            }

            return true;
        }

        return ! $this->isTooOld($publishedAt);
    }

    protected function marketKeywordHits(?string $text): array
    {
        $haystack = mb_strtolower((string) $text);
        if ($haystack === '') {
            return [];
        }

        return collect(self::MARKET_KEYWORDS)
            ->filter(fn ($keyword) => $keyword !== '' && str_contains($haystack, mb_strtolower($keyword)))
            ->unique()
            ->values()
            ->all();
    }

    /**
     * @return array{relevance_score: float, entity_match_score: float, market_context_score: float, final_quality_score: float}
     */
    protected function qualityScore(array $matchedKeywords, float $sourceWeight): array
    {
        $sourceWeights = (array) config('news.source_weights', []);
        $maxSourceWeight = max(1.0, max($sourceWeights ?: [1.0]));
        $normalizedSourceWeight = max(0.0, min(1.0, $sourceWeight / $maxSourceWeight));
        $keywordCount = count($matchedKeywords);

        $relevanceScore = min(0.72, 0.46 + ($keywordCount * 0.04));
        $entityScore = 0.18;
        $marketScore = min(0.88, 0.54 + ($keywordCount * 0.05));
        $finalQuality = (
            ($relevanceScore * 0.30) +
            ($entityScore * 0.12) +
            ($marketScore * 0.33) +
            (1.0 * 0.10) +
            ($normalizedSourceWeight * 0.15)
        );

        return [
            'relevance_score' => round(min(0.8, $relevanceScore), 3),
            'entity_match_score' => round($entityScore, 3),
            'market_context_score' => round($marketScore, 3),
            'final_quality_score' => round(min(0.9, $finalQuality), 3),
        ];
    }

    protected function qualityBand(float $score): string
    {
        $high = (float) config('news.quality_high', 0.55);
        $medium = (float) config('news.quality_medium', 0.40);

        if ($score >= $high) {
            return 'high';
        }

        return $score >= $medium ? 'medium' : 'low';
    }

    /**
     * @return array<int, array{title: string, source_url: string, listing_page: string}>
     */
    protected function parseHtmlListing(string $html, string $listingPage): array
    {
        libxml_use_internal_errors(true);
        $dom = new \DOMDocument();
        @$dom->loadHTML($html);
        libxml_clear_errors();

        $xpath = new \DOMXPath($dom);
        $nodes = $xpath->query('//a[@href]');
        if (! $nodes) {
            return [];
        }

        $items = [];
        foreach ($nodes as $node) {
            $href = trim((string) $node->getAttribute('href'));
            $title = trim(preg_replace('/\s+/u', ' ', (string) $node->textContent));
            if ($href === '' || $title === '') {
                continue;
            }

            if (! str_contains($href, '/siaran-pers/Pages/')) {
                continue;
            }

            $absoluteUrl = $this->resolveUrl($listingPage, $href);
            if (! $absoluteUrl) {
                continue;
            }

            $items[] = [
                'title' => html_entity_decode($title, ENT_QUOTES | ENT_HTML5),
                'source_url' => $absoluteUrl,
                'listing_page' => $listingPage,
            ];
        }

        return $items;
    }

    /**
     * @return array{
     *   items: array<int, array<string, mixed>>,
     *   form_inputs: array<string, string>,
     *   next_target: string|null,
     *   form_action: string|null
     * }
     */
    protected function parsePaginatedListingPage(string $html, string $listingPage): array
    {
        libxml_use_internal_errors(true);
        $dom = new \DOMDocument();
        @$dom->loadHTML($html);
        libxml_clear_errors();

        $xpath = new \DOMXPath($dom);
        $items = [];
        $anchors = $xpath->query('//a[contains(concat(" ", normalize-space(@class), " "), " group-item-title ")]');

        if ($anchors) {
            foreach ($anchors as $anchor) {
                if (! $anchor instanceof \DOMElement) {
                    continue;
                }

                $href = trim((string) $anchor->getAttribute('href'));
                $title = trim(preg_replace('/\s+/u', ' ', (string) $anchor->textContent));
                if ($href === '' || $title === '') {
                    continue;
                }

                $container = $this->resolveListingItemContainer($anchor);
                $dateText = $this->firstNodeText($xpath, './/div[contains(concat(" ", normalize-space(@class), " "), " date ")]', $container);
                $summary = $this->firstNodeText($xpath, './/div[contains(concat(" ", normalize-space(@class), " "), " caption ")]', $container);
                $publishedAt = $this->normalizeDateString($dateText);

                $items[] = [
                    'title' => html_entity_decode($title, ENT_QUOTES | ENT_HTML5),
                    'source_url' => $this->resolveUrl($listingPage, $href),
                    'listing_page' => $listingPage,
                    'summary' => $summary ?: $title,
                    'published_at' => $publishedAt,
                    'language' => str_contains($href, '/en/') ? 'en' : 'id',
                    'raw_date_text' => $dateText,
                ];
            }
        }

        $formInputs = [];
        $hiddenInputs = $xpath->query('//input[@type="hidden" and @name]');
        if ($hiddenInputs) {
            foreach ($hiddenInputs as $input) {
                if (! $input instanceof \DOMElement) {
                    continue;
                }

                $name = (string) $input->getAttribute('name');
                if ($name === '') {
                    continue;
                }

                $formInputs[$name] = (string) $input->getAttribute('value');
            }
        }

        $formAction = null;
        $formNode = $xpath->query('//form[@id="aspnetForm"]')->item(0);
        if ($formNode instanceof \DOMElement) {
            $action = trim((string) $formNode->getAttribute('action'));
            if ($action !== '') {
                $formAction = $this->resolveUrl($listingPage, $action);
            }
        }

        $currentPage = (int) ($this->firstNodeText($xpath, '//span[contains(concat(" ", normalize-space(@class), " "), " currentPagingButton ")]') ?: 1);
        $nextTarget = null;
        $paginationLinks = $xpath->query('//span[contains(concat(" ", normalize-space(@class), " "), " pagination ")]//a[contains(concat(" ", normalize-space(@class), " "), " pagingButton ")]');
        if ($paginationLinks) {
            $arrowTarget = null;

            foreach ($paginationLinks as $link) {
                if (! $link instanceof \DOMElement) {
                    continue;
                }

                $href = html_entity_decode((string) $link->getAttribute('href'), ENT_QUOTES | ENT_HTML5);
                $target = $this->extractPostBackTarget($href);
                if (! $target) {
                    continue;
                }

                $label = trim(preg_replace('/\s+/u', ' ', (string) $link->textContent));
                $className = (string) $link->getAttribute('class');

                if (is_numeric($label) && (int) $label === ($currentPage + 1)) {
                    $nextTarget = $target;
                    break;
                }

                if (str_contains($className, 'fa-arrow-right')) {
                    $arrowTarget = $target;
                }
            }

            $nextTarget ??= $arrowTarget;
        }

        return [
            'items' => $items,
            'form_inputs' => $formInputs,
            'next_target' => $nextTarget,
            'form_action' => $formAction,
        ];
    }

    /**
     * @param array{title: string, source_url: string, listing_page?: string} $candidate
     * @return array{title: string, summary: string, full_text: string, published_at: Carbon, language: string}|null
     */
    protected function hydrateHtmlCandidate(array $candidate, int $timeout, string $userAgent): ?array
    {
        try {
            $response = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            ])->timeout(max($timeout, 12))->get($candidate['source_url']);
        } catch (\Throwable $e) {
            Log::warning('OJK article hydration failed', ['url' => $candidate['source_url'], 'error' => $e->getMessage()]);
            return null;
        }

        if (! $response->successful()) {
            Log::warning('OJK article hydration non-success', ['url' => $candidate['source_url'], 'status' => $response->status()]);
            return null;
        }

        $html = $response->body();
        $text = trim(preg_replace('/\s+/u', ' ', html_entity_decode(strip_tags($html), ENT_QUOTES | ENT_HTML5)));
        if ($text === '') {
            return null;
        }

        $title = $this->extractMetaTitle($html) ?: $candidate['title'];
        $summary = $this->extractMetaDescription($html);
        if (! $summary) {
            $summary = Str::limit($text, 500);
        }

        $publishedAt = $this->extractPublishedAtFromText($summary.' '.$text) ?? Carbon::now('Asia/Jakarta');
        $language = str_contains($candidate['source_url'], '/en/') || str_starts_with($title, 'Press Release:')
            ? 'en'
            : 'id';

        return [
            'title' => $title,
            'summary' => $summary,
            'full_text' => Str::limit($text, 2000),
            'published_at' => $publishedAt,
            'language' => $language,
        ];
    }

    protected function fetchHtmlDocument(string $url, int $timeout, string $userAgent): ?string
    {
        try {
            $response = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            ])->timeout(max($timeout, 12))->get($url);
        } catch (\Throwable $e) {
            Log::warning('OJK HTML document fetch failed', ['url' => $url, 'error' => $e->getMessage()]);

            return null;
        }

        if (! $response->successful()) {
            Log::warning('OJK HTML document fetch non-success', ['url' => $url, 'status' => $response->status()]);

            return null;
        }

        return $response->body();
    }

    protected function postListingPage(
        string $url,
        array $formInputs,
        string $eventTarget,
        int $timeout,
        string $userAgent
    ): ?string {
        $payload = $formInputs;
        $payload['__EVENTTARGET'] = $eventTarget;
        $payload['__EVENTARGUMENT'] = '';

        try {
            $response = Http::asForm()
                ->withHeaders([
                    'User-Agent' => $userAgent,
                    'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer' => $url,
                ])->timeout(max($timeout, 12))
                ->post($url, $payload);
        } catch (\Throwable $e) {
            Log::warning('OJK listing pagination request failed', [
                'url' => $url,
                'event_target' => $eventTarget,
                'error' => $e->getMessage(),
            ]);

            return null;
        }

        if (! $response->successful()) {
            Log::warning('OJK listing pagination non-success', [
                'url' => $url,
                'event_target' => $eventTarget,
                'status' => $response->status(),
            ]);

            return null;
        }

        return $response->body();
    }

    protected function extractMetaTitle(string $html): ?string
    {
        if (preg_match('/<title>\s*(.*?)\s*<\/title>/is', $html, $matches)) {
            return trim(html_entity_decode(strip_tags($matches[1]), ENT_QUOTES | ENT_HTML5));
        }

        return null;
    }

    protected function extractMetaDescription(string $html): ?string
    {
        if (preg_match('/<meta\s+name="description"\s+content="([^"]+)"/i', $html, $matches)) {
            return trim(html_entity_decode($matches[1], ENT_QUOTES | ENT_HTML5));
        }

        return null;
    }

    protected function extractPublishedAtFromText(string $text): ?Carbon
    {
        $patterns = [
            '/\b\d{4}-\d{2}-\d{2}\b/',
            '/\b\d{1,2}\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b/ui',
            '/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b/ui',
        ];

        foreach ($patterns as $pattern) {
            if (! preg_match($pattern, $text, $matches)) {
                continue;
            }

            $parsed = $this->normalizeDateString($matches[0] ?? null);
            if ($parsed) {
                return $parsed;
            }
        }

        return null;
    }

    protected function normalizeDateString(?string $dateText): ?Carbon
    {
        if (! $dateText) {
            return null;
        }

        $normalized = str_ireplace([
            'Januari', 'Februari', 'Maret', 'Mei', 'Juni', 'Juli',
            'Agustus', 'Oktober', 'Desember',
        ], [
            'January', 'February', 'March', 'May', 'June', 'July',
            'August', 'October', 'December',
        ], $dateText);

        $normalized = str_ireplace([
            'April', 'September', 'November',
            'Agustus', 'Oktober', 'Desember',
        ], [
            'April', 'September', 'November',
            'August', 'October', 'December',
        ], $normalized);

        $normalized = str_ireplace([
            'Mei', 'Juni', 'Juli',
            'Februari', 'Maret',
        ], [
            'May', 'June', 'July',
            'February', 'March',
        ], $normalized);

        try {
            return Carbon::parse($normalized, 'Asia/Jakarta');
        } catch (\Throwable) {
            return null;
        }
    }

    protected function resolveUrl(string $baseUrl, string $href): ?string
    {
        if ($href === '') {
            return null;
        }

        if (str_starts_with($href, './')) {
            $href = substr($href, 2);
        }

        if (str_starts_with($href, 'http://') || str_starts_with($href, 'https://')) {
            return $href;
        }

        if (str_starts_with($href, '/')) {
            $scheme = parse_url($baseUrl, PHP_URL_SCHEME) ?: 'https';
            $host = parse_url($baseUrl, PHP_URL_HOST);

            return $host ? $scheme.'://'.$host.$href : null;
        }

        return rtrim($baseUrl, '/').'/'.ltrim($href, '/');
    }

    protected function extractPostBackTarget(?string $href): ?string
    {
        if (! $href) {
            return null;
        }

        if (! preg_match("/__doPostBack\\('([^']+)'/i", $href, $matches)) {
            return null;
        }

        return html_entity_decode($matches[1], ENT_QUOTES | ENT_HTML5);
    }

    protected function firstNodeText(?\DOMXPath $xpath, string $expression, ?\DOMNode $contextNode = null): string
    {
        if (! $xpath) {
            return '';
        }

        $nodes = $xpath->query($expression, $contextNode);
        if (! $nodes || $nodes->length === 0) {
            return '';
        }

        return trim(preg_replace('/\s+/u', ' ', (string) $nodes->item(0)?->textContent));
    }

    protected function resolveListingItemContainer(\DOMElement $anchor): ?\DOMElement
    {
        $current = $anchor->parentNode;

        while ($current instanceof \DOMElement) {
            $className = ' '.trim((string) $current->getAttribute('class')).' ';
            if (str_contains($className, ' col-lg-10 ')
                || str_contains($className, ' col-md-10 ')
                || str_contains($className, ' article-list-view-wrap ')
            ) {
                return $current;
            }

            $current = $current->parentNode;
        }

        return $anchor->parentNode instanceof \DOMElement ? $anchor->parentNode : null;
    }

    /**
     * @return array{0: CarbonInterface|null, 1: CarbonInterface|null}
     */
    protected function resolveWindow(
        CarbonInterface|string|null $from,
        CarbonInterface|string|null $to
    ): array {
        $fromDate = $from instanceof CarbonInterface
            ? $from->copy()->startOfDay()
            : (is_string($from) && trim($from) !== '' ? Carbon::parse($from)->startOfDay() : null);
        $toDate = $to instanceof CarbonInterface
            ? $to->copy()->endOfDay()
            : (is_string($to) && trim($to) !== '' ? Carbon::parse($to)->endOfDay() : null);

        if ($fromDate && $toDate && $fromDate->gt($toDate)) {
            [$fromDate, $toDate] = [$toDate->copy()->startOfDay(), $fromDate->copy()->endOfDay()];
        }

        return [$fromDate, $toDate];
    }

    /**
     * @return array{from: string|null, to: string|null}
     */
    protected function windowPayload(?CarbonInterface $fromDate, ?CarbonInterface $toDate): array
    {
        return [
            'from' => $fromDate?->toDateString(),
            'to' => $toDate?->toDateString(),
        ];
    }

    /**
     * @return array<int, array<string, string>>
     */
    protected function parseFeedItems(string $xmlString, string $feedUrl): array
    {
        libxml_use_internal_errors(true);
        $xml = @simplexml_load_string($xmlString, 'SimpleXMLElement', LIBXML_NOCDATA);
        $errors = libxml_get_errors();
        libxml_clear_errors();

        if (! $xml || $errors) {
            Log::warning('OJK RSS invalid XML', [
                'feed' => $feedUrl,
                'errors' => collect($errors)->pluck('message')->take(2)->all(),
            ]);
            return [];
        }

        $items = [];
        if (isset($xml->channel->item)) {
            foreach ($xml->channel->item as $item) {
                $items[] = [
                    'title' => (string) ($item->title ?? ''),
                    'description' => (string) ($item->description ?? ''),
                    'link' => (string) ($item->link ?? ''),
                    'pubDate' => (string) ($item->pubDate ?? ''),
                ];
            }
        } elseif (isset($xml->entry)) {
            foreach ($xml->entry as $item) {
                $items[] = [
                    'title' => (string) ($item->title ?? ''),
                    'description' => (string) ($item->summary ?? ''),
                    'link' => (string) (isset($item->link['href']) ? $item->link['href'] : ($item->link ?? '')),
                    'pubDate' => (string) ($item->updated ?? $item->published ?? ''),
                ];
            }
        }

        return $items;
    }
}
