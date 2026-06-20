<?php

namespace App\Services\News;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use App\Services\News\ApiNewsFetcher;
use App\Services\News\FinnhubNewsFetcher;
use App\Services\News\GdeltFetcher;
use App\Services\News\GNewsFetcher;
use App\Services\News\GoogleNewsRssFetcher;
use App\Services\News\IdxDisclosureFetcher;
use App\Services\News\ManualNewsFetcher;
use App\Services\News\BusinessSiteSearchFetcher;
use App\Services\News\MockNewsFetcher;
use App\Services\News\NewsApiFetcher;
use App\Services\News\OjkRssFetcher;
use App\Services\News\RssLocalFetcher;
use App\Services\News\RssNewsFetcher;
use App\Services\News\StockKeywordMapper;
use App\Services\News\RelevanceScoringService;
use App\Services\News\ArticleDeduplicationService;
use App\Services\Sentiment\SentimentAnalyzerInterface;
use App\Services\Sentiment\SentimentEngineManager;
use App\Models\SystemSetting;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class NewsAggregationService
{
    private const NEWS_ARTICLE_SLUG_MAX_LENGTH = 220;
    private const NEWS_ARTICLE_STRING_MAX_LENGTH = 255;

    /**
     * @var array<string, NewsFetcherInterface>
     */
    protected array $fetchers = [];

    public function __construct(
        protected ?SentimentAnalyzerInterface $analyzer = null,
        protected ?StockKeywordMapper $keywordMapper = null,
        protected ?SentimentEngineManager $sentimentEngineManager = null,
        protected ?RelevanceScoringService $relevanceScoringService = null,
        protected ?ArticleDeduplicationService $deduper = null,
    ) {
        $this->sentimentEngineManager ??= new SentimentEngineManager();
        $this->analyzer ??= $this->sentimentEngineManager->getAnalyzer();
        $this->keywordMapper ??= new StockKeywordMapper();
        $this->relevanceScoringService ??= new RelevanceScoringService($this->keywordMapper);
        $this->deduper ??= new ArticleDeduplicationService();
        $this->fetchers = [
            'mock' => new MockNewsFetcher(),
            'manual' => new ManualNewsFetcher(),
            'rss' => new RssNewsFetcher(),
            'api' => new ApiNewsFetcher(),
            'finnhub' => new FinnhubNewsFetcher(),
            'google_news_rss' => new GoogleNewsRssFetcher($this->keywordMapper),
            'idx_disclosure' => new IdxDisclosureFetcher(),
            'business_site_search' => new BusinessSiteSearchFetcher($this->keywordMapper),
            'newsapi' => new NewsApiFetcher($this->keywordMapper),
            'gnews' => new GNewsFetcher($this->keywordMapper),
            'ojk' => new OjkRssFetcher(),
            'rss_local' => new RssLocalFetcher($this->keywordMapper),
            'gdelt' => new GdeltFetcher($this->keywordMapper),
        ];
    }

    public function fetchLatestArticles(Stock $stock, int $limit = 10)
    {
        return NewsArticle::with('source')
            ->forStockContext($stock)
            ->orderByDesc('final_quality_score')
            ->orderByDesc('published_at')
            ->limit($limit)
            ->get();
    }

    public function refreshFromProvider(Stock $stock, int $limit = 5, ?array $providerOverride = null): array
    {
        $providerKey = data_get(SystemSetting::where('key', 'news_provider')->first(), 'value.value')
            ?? config('services.news.provider', env('NEWS_PROVIDER', 'mock'));

        $preferred = config('news.preferred_providers.'.($stock->code ?? ''), null);
        $providers = $providerOverride ?: ($providerKey === 'multi'
            ? ($preferred ?: config('news.multi_providers', config('news.source_priority', ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'ojk', 'gnews', 'newsapi', 'finnhub', 'gdelt'])))
            : [$providerKey]);

        $rawArticles = collect();
        $stats = $this->baseStats();
        foreach ($providers as $key) {
            $fetcher = $this->fetchers[$key] ?? null;
            if (! $fetcher) {
                continue;
            }
            $providerKeyName = match ($key) {
                'api' => 'newsapi_legacy',
                'ojk' => 'ojk_rss',
                default => $key,
            };
            $fetched = collect($fetcher->fetchForStock($stock, $limit))->map(function ($item) use ($providerKeyName) {
                $item['provider'] = $item['provider'] ?? $providerKeyName;
                return $item;
            });

            $stats['raw'] += $fetched->count();
            $stats['by_provider'][$providerKeyName] = ($stats['by_provider'][$providerKeyName] ?? 0) + $fetched->count();

            $rawArticles = $rawArticles->merge($fetched);
        }

        return $this->persistRawArticles($stock, $rawArticles, $stats, $providerKey);
    }

    public function refreshOjkBackfill(
        Stock $stock,
        CarbonInterface|string $from,
        CarbonInterface|string $to,
        int $limit = 100,
        ?int $candidateLimit = null
    ): array {
        $fetcher = $this->fetchers['ojk'] ?? new OjkRssFetcher();
        if (! method_exists($fetcher, 'fetchForMarketInRange')) {
            return $this->baseStats();
        }

        $rawArticles = collect($fetcher->fetchForMarketInRange($from, $to, $limit, $candidateLimit));
        $stats = $this->baseStats();
        $stats['raw'] = $rawArticles->count();
        $stats['by_provider']['ojk_rss'] = $rawArticles->count();

        return $this->persistRawArticles($stock, $rawArticles, $stats, 'ojk_rss');
    }

    public function persistHistoricalArticles(Stock $stock, array $articles, string $providerKey): array
    {
        $rawArticles = collect($articles)->map(function ($item) use ($providerKey) {
            $item['provider'] = $item['provider'] ?? $providerKey;
            return $item;
        });

        $stats = $this->baseStats();
        $stats['raw'] = $rawArticles->count();
        $stats['by_provider'][$providerKey] = $rawArticles->count();

        return $this->persistRawArticles($stock, $rawArticles, $stats, $providerKey);
    }

    protected function baseStats(): array
    {
        return [
            'raw' => 0,
            'by_provider' => [],
            'filtered' => 0,
            'dropped_language' => 0,
            'dropped_relevance' => 0,
            'dropped_quality' => 0,
            'dropped_exclusion' => 0,
            'dropped_irrelevant' => 0,
            'skipped_dedup' => 0,
            'saved' => 0,
            'updated' => 0,
            'failed' => 0,
            'kept_score_sum' => 0.0,
            'kept_score_count' => 0,
            'drop_score_sum' => 0.0,
            'drop_score_count' => 0,
            'band_high' => 0,
            'band_medium' => 0,
            'band_low' => 0,
            'drop_relevance_sum' => 0.0,
            'drop_entity_sum' => 0.0,
            'drop_market_sum' => 0.0,
            'kept_relevance_sum' => 0.0,
            'kept_entity_sum' => 0.0,
            'kept_market_sum' => 0.0,
            'dropped_samples' => [
                'relevance' => [],
                'quality' => [],
                'exclusion' => [],
            ],
        ];
    }

    protected function persistRawArticles(
        Stock $stock,
        \Illuminate\Support\Collection $rawArticles,
        array $stats,
        ?string $providerKey = null
    ): array {
        $keywords = $this->keywordMapper->keywords($stock);

        $exclusions = $this->keywordMapper->exclusionKeywords($stock);
        $domainWhitelist = $this->domainList(env('NEWS_DOMAIN_WHITELIST', ''));
        $domainBlacklist = $this->domainList(env('NEWS_DOMAIN_BLACKLIST', ''));
        $threshold = (float) config('news.relevance_threshold', 0.35);
        $finalThreshold = (float) config('news.final_quality_threshold', 0.4);
        $this->deduper->reset();

        $scoredArticles = collect();

        foreach ($rawArticles as $raw) {
            $domainDecision = $this->domainAndExclusionDecision($raw, $exclusions, $domainWhitelist, $domainBlacklist);
            if (! ($domainDecision['passed'] ?? false)) {
                $stats['dropped_exclusion']++;
                $this->pushDroppedSample($stats, 'exclusion', [
                    'title' => $raw['title'] ?? '(no title)',
                    'provider' => $raw['provider'] ?? $providerKey ?? 'unknown',
                    'reason' => $domainDecision['reason'] ?? 'excluded',
                    'detail' => $domainDecision['detail'] ?? null,
                    'source_domain' => $this->extractDomain($raw['source_url'] ?? null),
                ]);
                continue;
            }

            if (! ($raw['skip_relevance_rescore'] ?? false)) {
                $score = $this->relevanceScoringService->score($stock, $raw, $raw['provider'] ?? null);
                $raw = array_merge($raw, $score);
            }

            $lang = strtolower($raw['detected_language'] ?? $raw['language'] ?? '');
            if ($lang && ! in_array($lang, ['id', 'en'])) {
                $stats['dropped_language']++;
                $stats['drop_relevance_sum'] += $raw['relevance_score'] ?? 0;
                $stats['drop_entity_sum'] += $raw['entity_match_score'] ?? 0;
                $stats['drop_market_sum'] += $raw['market_context_score'] ?? 0;
                continue;
            }

            $isRss = ($raw['provider'] ?? '') === 'rss_local';
            $hasDirectIssuerMatch = ($raw['issuer_specificity'] ?? null) === 'direct';
            $isMacroRegulatory = $this->isMacroRegulatory($raw);
            $passRelevance = ($hasDirectIssuerMatch
                && (($raw['relevance_score'] ?? 0) >= ($isRss ? 0.15 : $threshold)))
                || ($isMacroRegulatory && (($raw['relevance_score'] ?? 0) >= max(0.40, $threshold)));

            if (! $passRelevance) {
                $stats['dropped_relevance']++;
                $stats['drop_relevance_sum'] += $raw['relevance_score'] ?? 0;
                $stats['drop_entity_sum'] += $raw['entity_match_score'] ?? 0;
                $stats['drop_market_sum'] += $raw['market_context_score'] ?? 0;
                $this->pushDroppedSample($stats, 'relevance', [
                    'title' => $raw['title'] ?? '(no title)',
                    'provider' => $raw['provider'] ?? $providerKey ?? 'unknown',
                    'reason' => 'relevance_below_threshold',
                    'relevance' => round((float) ($raw['relevance_score'] ?? 0), 3),
                    'entity' => round((float) ($raw['entity_match_score'] ?? 0), 3),
                    'market' => round((float) ($raw['market_context_score'] ?? 0), 3),
                    'issuer_specificity' => $raw['issuer_specificity'] ?? 'none',
                    'direct_keyword_hits' => $raw['direct_keyword_hits'] ?? [],
                    'competing_keyword_hits' => $raw['competing_keyword_hits'] ?? [],
                ]);
                continue;
            }

            $finalScore = $raw['final_quality_score'] ?? $raw['relevance_score'] ?? 0;
            if ($finalScore < $finalThreshold) {
                $stats['dropped_quality']++;
                $stats['drop_score_sum'] += $finalScore;
                $stats['drop_score_count']++;
                $this->pushDroppedSample($stats, 'quality', [
                    'title' => $raw['title'] ?? '(no title)',
                    'provider' => $raw['provider'] ?? $providerKey ?? 'unknown',
                    'reason' => 'quality_below_threshold',
                    'final_quality' => round((float) $finalScore, 3),
                    'relevance' => round((float) ($raw['relevance_score'] ?? 0), 3),
                    'issuer_specificity' => $raw['issuer_specificity'] ?? 'none',
                ]);
                continue;
            }

            $stats['filtered']++;
            $scoredArticles->push($raw);
        }

        $scoredArticles = $scoredArticles->sortByDesc('final_quality_score')->values();

        foreach ($scoredArticles as $rawArticle) {
            try {
                if ($this->deduper->shouldSkip($rawArticle)) {
                    $stats['skipped_dedup']++;
                    continue;
                }

                if (! $this->isRelevant($rawArticle, $keywords)) {
                    $stats['dropped_irrelevant']++;
                    continue;
                }

                $title = $rawArticle['title'] ?? 'Berita '.$stock->code;
                $slug = $this->normalizeArticleSlug($rawArticle['slug'] ?? $title);
                $storedTitle = Str::limit($title, self::NEWS_ARTICLE_STRING_MAX_LENGTH, '');
                $summary = $rawArticle['summary'] ?? $title;
                $analysis = $this->analyzer->analyze($summary, [
                    'title' => $title,
                    'summary' => $summary,
                    'body' => $rawArticle['full_text'] ?? $rawArticle['content_snippet'] ?? null,
                    'language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
                ]);
                $sourceUrl = $this->normalizeArticleSourceUrl($rawArticle['source_url'] ?? null, $slug);

                // Pastikan slug unik jika sudah ada, tapi gunakan source_url sebagai key utama jika tersedia.
                if ($sourceUrl) {
                    $match = ['source_url' => $sourceUrl];
                } else {
                    if (NewsArticle::where('slug', $slug)->exists()) {
                        $slug = $this->appendSlugSuffix($slug, Str::random(4));
                    }
                    $match = ['slug' => $slug];
                }

                $finalQuality = $rawArticle['final_quality_score'] ?? $rawArticle['relevance_score'] ?? null;
                $qualityBand = $rawArticle['quality_band'] ?? null;
                if (! $qualityBand && $finalQuality !== null) {
                    $qualityBand = $finalQuality >= (float) config('news.quality_high', 0.7)
                        ? 'high'
                        : (($finalQuality >= (float) config('news.quality_medium', 0.5)) ? 'medium' : 'low');
                }

                $providerValue = $rawArticle['provider'] ?? $providerKey ?? 'unknown';
                if ($providerValue === 'api') {
                    $providerValue = 'newsapi_legacy';
                }
                if (! $providerValue) {
                    $providerValue = 'unknown';
                }
                $source = $this->resolveSource($providerValue);

                $model = NewsArticle::updateOrCreate($match, [
                    'slug' => $slug,
                    'stock_id' => $this->shouldStoreGlobally($rawArticle) ? null : $stock->id,
                    'news_source_id' => $source?->id,
                    'source_provider' => $providerValue,
                    'source_weight' => $rawArticle['source_weight'] ?? null,
                    'title' => $storedTitle,
                    'source_url' => $sourceUrl,
                    'published_at' => $rawArticle['published_at'] ?? Carbon::now(),
                    'summary' => $summary,
                    'content_snippet' => $rawArticle['content_snippet'] ?? null,
                    'full_text' => $rawArticle['full_text'] ?? null,
                    'sentiment_label' => $rawArticle['sentiment_label'] ?? $analysis['label'],
                    'sentiment_score' => $rawArticle['sentiment_score'] ?? $analysis['score'],
                    'sentiment_confidence' => $rawArticle['sentiment_confidence'] ?? $analysis['confidence'] ?? null,
                    'sentiment_method' => $rawArticle['sentiment_method'] ?? $analysis['method'] ?? 'python_unavailable',
                    'ml_sentiment_label' => $rawArticle['ml_sentiment_label'] ?? $analysis['ml_label'] ?? null,
                    'ml_sentiment_score' => $rawArticle['ml_sentiment_score'] ?? $analysis['ml_score'] ?? null,
                    'ml_confidence' => $rawArticle['ml_confidence'] ?? $analysis['ml_confidence'] ?? null,
                    'ml_prob_positive' => $rawArticle['ml_prob_positive'] ?? $analysis['ml_prob_positive'] ?? null,
                    'ml_prob_neutral' => $rawArticle['ml_prob_neutral'] ?? $analysis['ml_prob_neutral'] ?? null,
                    'ml_prob_negative' => $rawArticle['ml_prob_negative'] ?? $analysis['ml_prob_negative'] ?? null,
                    'rule_sentiment_label' => $rawArticle['rule_sentiment_label'] ?? $analysis['rule_label'] ?? null,
                    'rule_sentiment_score' => $rawArticle['rule_sentiment_score'] ?? $analysis['rule_score'] ?? null,
                    'ml_rule_agree' => $rawArticle['ml_rule_agree']
                        ?? (isset($analysis['ml_label'], $analysis['rule_label']) ? $analysis['ml_label'] === $analysis['rule_label'] : null),
                    'relevance_score' => $rawArticle['relevance_score'] ?? null,
                    'relevance_band' => $rawArticle['relevance_band'] ?? null,
                    'entity_match_score' => $rawArticle['entity_match_score'] ?? null,
                    'market_context_score' => $rawArticle['market_context_score'] ?? null,
                    'language_score' => $rawArticle['language_score'] ?? null,
                    'final_quality_score' => $finalQuality,
                    'quality_band' => $qualityBand,
                    'matched_keywords' => $rawArticle['matched_keywords'] ?? null,
                    'quality_flags' => $rawArticle['quality_flags'] ?? null,
                    'sentiment_meta' => [
                        'matched_positive_terms' => $analysis['matched_positive_terms'] ?? [],
                        'matched_negative_terms' => $analysis['matched_negative_terms'] ?? [],
                        'reason_summary' => $analysis['reason_summary'] ?? null,
                        'python_status' => $analysis['python_status'] ?? null,
                    ],
                    'analyzed_at' => Carbon::now(),
                    'language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
                    'detected_language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
                    'raw_payload' => $rawArticle['raw_payload'] ?? null,
                    'fetched_at' => Carbon::now(),
                ]);

                if ($finalQuality !== null) {
                    $stats['kept_score_sum'] += $finalQuality;
                    $stats['kept_score_count']++;
                }
                if ($qualityBand === 'high') {
                    $stats['band_high']++;
                } elseif ($qualityBand === 'medium') {
                    $stats['band_medium']++;
                } else {
                    $stats['band_low']++;
                }
                $stats['kept_relevance_sum'] += $rawArticle['relevance_score'] ?? 0;
                $stats['kept_entity_sum'] += $rawArticle['entity_match_score'] ?? 0;
                $stats['kept_market_sum'] += $rawArticle['market_context_score'] ?? 0;

                $model->wasRecentlyCreated ? $stats['saved']++ : $stats['updated']++;
            } catch (\Throwable $e) {
                $stats['failed']++;
                Log::warning('News article persist failed; skipping article and continuing batch', [
                    'error' => $e->getMessage(),
                    'stock' => $stock->code ?? null,
                    'provider' => $rawArticle['provider'] ?? $providerKey ?? 'unknown',
                    'title' => Str::limit((string) ($rawArticle['title'] ?? ''), 180),
                    'source_url' => $rawArticle['source_url'] ?? null,
                ]);
            }
        }

        return $stats;
    }

    protected function domainAndExclusionDecision(array $rawArticle, array $exclusions, array $domainWhitelist, array $domainBlacklist): array
    {
        $domain = $this->extractDomain($rawArticle['source_url'] ?? null);
        if ($domain && in_array($domain, $domainBlacklist, true)) {
            return [
                'passed' => false,
                'reason' => 'domain_blacklisted',
                'detail' => $domain,
            ];
        }
        if ($domainWhitelist && $domain && ! in_array($domain, $domainWhitelist, true)) {
            return [
                'passed' => false,
                'reason' => 'domain_not_whitelisted',
                'detail' => $domain,
            ];
        }

        if ($this->isMacroRegulatory($rawArticle)) {
            return ['passed' => true];
        }

        $text = strtolower(implode(' ', array_filter([
            $rawArticle['title'] ?? '',
            $rawArticle['summary'] ?? '',
            $rawArticle['content_snippet'] ?? '',
            $rawArticle['full_text'] ?? '',
        ])));

        foreach ($exclusions as $ex) {
            if ($ex && str_contains($text, strtolower($ex))) {
                return [
                    'passed' => false,
                    'reason' => 'matched_exclusion_keyword',
                    'detail' => $ex,
                ];
            }
        }

        return ['passed' => true];
    }

    protected function passesDomainAndExclusion(array $rawArticle, array $exclusions, array $domainWhitelist, array $domainBlacklist): bool
    {
        return (bool) ($this->domainAndExclusionDecision($rawArticle, $exclusions, $domainWhitelist, $domainBlacklist)['passed'] ?? false);
    }

    protected function pushDroppedSample(array &$stats, string $bucket, array $sample, int $limit = 3): void
    {
        if (! isset($stats['dropped_samples'][$bucket]) || ! is_array($stats['dropped_samples'][$bucket])) {
            $stats['dropped_samples'][$bucket] = [];
        }

        if (count($stats['dropped_samples'][$bucket]) >= $limit) {
            return;
        }

        $stats['dropped_samples'][$bucket][] = $sample;
    }

    protected function isRelevant(array $rawArticle, array $keywords): bool
    {
        $text = strtolower(implode(' ', array_filter([
            $rawArticle['title'] ?? '',
            $rawArticle['summary'] ?? '',
            $rawArticle['content_snippet'] ?? '',
            $rawArticle['full_text'] ?? '',
        ])));

        if ($this->isMacroRegulatory($rawArticle)) {
            return true;
        }

        // Language gate: reject foreign diacritics / non-ID/EN
        $foreignPattern = '/[àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿčšžřůďťľščňě]/u';
        if (preg_match($foreignPattern, $rawArticle['title'] ?? '')) {
            return false;
        }
        $indonesianMarkers = [' dan ', ' di ', ' ke ', ' dari ', ' yang ', ' untuk ', ' dengan ', ' ini ', ' itu ', ' pada ', ' adalah ', ' akan ', ' tidak ', ' juga ', ' the ', ' of ', ' in ', ' to ', ' and ', ' for ', ' a '];
        $titleLower = strtolower(' '.($rawArticle['title'] ?? '').' ');
        $hasMarker = false;
        foreach ($indonesianMarkers as $marker) {
            if (str_contains($titleLower, $marker)) {
                $hasMarker = true;
                break;
            }
        }
        if (! $hasMarker && strlen(trim($titleLower)) > 20) {
            return false;
        }

        // Hard exclude untuk BUMI saham: cegah artikel "planet bumi" masuk
        // Jika keyword stock adalah nama umum (bumi, goto, dll), 
        // wajibkan konteks finansial
        $titleLower = strtolower($rawArticle['title'] ?? '');
        $nonFinancialPatterns = [
            'planet', 'astronaut', 'artemis', 'nasa', 'antariksa', 'luar angkasa',
            'bulan purnama', 'gerhana', 'meteor', 'bintang',
            'ular berbisa', 'king cobra', 'hewan', 'binatang',
            'resep', 'masakan', 'kuliner', 'wisata', 'liburan',
            'film', 'drama', 'artis', 'selebriti', 'musik',
            'sepak bola', 'timnas', 'piala dunia',
            'cuaca', 'hujan', 'banjir', 'gempa',
        ];
        foreach ($nonFinancialPatterns as $pattern) {
            if (str_contains($titleLower, $pattern)) {
                return false;
            }
        }

        $excludeKeywords = [
            'langit', 'roket', 'bencana alam', 'gempa', 'banjir', 'kebakaran',
            'artis', 'selebriti', 'viral', 'tiktok', 'instagram', 'youtube',
            'sepak bola', 'timnas', 'liga', 'piala', 'olahraga',
            'resep', 'kuliner', 'wisata', 'pariwisata',
            'cuaca', 'prakiraan', 'bmkg',
            'astronaut', 'artemis', 'nasa', 'antariksa', 'luar angkasa',
            'planet', 'gerhana', 'meteor', 'satelit', 'orbit',
            'king cobra', 'ular berbisa', 'hewan liar', 'spesies',
            'mendarat di bumi', 'bumi dari bulan', 'keliling bulan',
        ];
        foreach ($excludeKeywords as $excl) {
            if (str_contains($text, $excl)) {
                return false;
            }
        }

        if (($rawArticle['issuer_specificity'] ?? null) !== 'direct') {
            return false;
        }

        if (! empty($rawArticle['competing_keyword_hits']) && empty($rawArticle['direct_keyword_hits'])) {
            return false;
        }

        if (! empty($rawArticle['direct_keyword_hits'])) {
            return true;
        }

        foreach ($keywords as $kw) {
            if ($kw && str_contains($text, strtolower($kw))) {
                return true;
            }
        }

        return false;
    }

    protected function extractDomain(?string $url): ?string
    {
        if (! $url) {
            return null;
        }
        $host = parse_url($url, PHP_URL_HOST);
        return $host ? strtolower($host) : null;
    }

    protected function domainList(string $csv): array
    {
        return collect(preg_split('/[;,]/', $csv))
            ->map(fn ($d) => trim(strtolower($d)))
            ->filter()
            ->unique()
            ->values()
            ->all();
    }

    protected function resolveSource(string $providerKey): ?NewsSource
    {
        $displayName = match ($providerKey) {
            'ojk_rss' => 'OJK RSS',
            'newsapi_legacy' => 'NewsAPI Legacy',
            default => Str::title(str_replace('_', ' ', $providerKey)).' Provider',
        };

        return NewsSource::firstOrCreate(
            ['name' => $displayName],
            [
                'type' => $providerKey,
                'is_active' => true,
                'config_json' => ['seeded' => true],
            ]
        );
    }

    protected function normalizeArticleSlug(string $value): string
    {
        $slug = Str::slug($value) ?: Str::random(8);

        if (mb_strlen($slug) <= self::NEWS_ARTICLE_SLUG_MAX_LENGTH) {
            return $slug;
        }

        return $this->appendSlugSuffix($slug, substr(sha1($value), 0, 10));
    }

    protected function appendSlugSuffix(string $slug, string $suffix): string
    {
        $suffix = trim($suffix, '-');
        $suffixLength = mb_strlen($suffix) + 1;
        $baseLength = max(1, self::NEWS_ARTICLE_SLUG_MAX_LENGTH - $suffixLength);

        return rtrim(Str::limit($slug, $baseLength, ''), '-').'-'.$suffix;
    }

    protected function normalizeArticleSourceUrl(?string $sourceUrl, string $slug): string
    {
        $sourceUrl = trim((string) $sourceUrl);
        if ($sourceUrl === '') {
            return 'https://news.local/'.$slug;
        }

        if (mb_strlen($sourceUrl) <= self::NEWS_ARTICLE_STRING_MAX_LENGTH) {
            return $sourceUrl;
        }

        return 'https://news.local/external-'.substr(sha1($sourceUrl), 0, 24);
    }

    protected function isMacroRegulatory(array $rawArticle): bool
    {
        return ($rawArticle['provider'] ?? null) === 'ojk_rss'
            && ($rawArticle['issuer_specificity'] ?? null) === 'macro_regulatory';
    }

    protected function shouldStoreGlobally(array $rawArticle): bool
    {
        return $this->isMacroRegulatory($rawArticle);
    }
}
