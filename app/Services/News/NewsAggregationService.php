<?php

namespace App\Services\News;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use App\Services\News\ApiNewsFetcher;
use App\Services\News\FinnhubNewsFetcher;
use App\Services\News\GdeltFetcher;
use App\Services\News\GNewsFetcher;
use App\Services\News\ManualNewsFetcher;
use App\Services\News\MockNewsFetcher;
use App\Services\News\NewsApiFetcher;
use App\Services\News\RssLocalFetcher;
use App\Services\News\RssNewsFetcher;
use App\Services\News\StockKeywordMapper;
use App\Services\News\RelevanceScoringService;
use App\Services\News\ArticleDeduplicationService;
use App\Services\Sentiment\SentimentAnalyzerInterface;
use App\Services\Sentiment\SentimentEngineManager;
use App\Models\SystemSetting;
use Carbon\Carbon;
use Illuminate\Support\Str;

class NewsAggregationService
{
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
            'newsapi' => new NewsApiFetcher($this->keywordMapper),
            'gnews' => new GNewsFetcher($this->keywordMapper),
            'rss_local' => new RssLocalFetcher($this->keywordMapper),
            'gdelt' => new GdeltFetcher($this->keywordMapper),
        ];
    }

    public function fetchLatestArticles(Stock $stock, int $limit = 10)
    {
        return NewsArticle::with('source')
            ->where('stock_id', $stock->id)
            ->orderByDesc('final_quality_score')
            ->orderByDesc('published_at')
            ->limit($limit)
            ->get();
    }

    public function refreshFromProvider(Stock $stock, int $limit = 5): void
    {
        $providerKey = data_get(SystemSetting::where('key', 'news_provider')->first(), 'value.value')
            ?? config('services.news.provider', env('NEWS_PROVIDER', 'mock'));

        $providers = $providerKey === 'multi'
            ? (config('news.source_priority', ['newsapi', 'gnews', 'rss_local', 'gdelt', 'finnhub']))
            : [$providerKey];

        $rawArticles = collect();
        foreach ($providers as $key) {
            $fetcher = $this->fetchers[$key] ?? null;
            if (! $fetcher) {
                continue;
            }
            $rawArticles = $rawArticles->merge(
                collect($fetcher->fetchForStock($stock, $limit))->map(function ($item) use ($key) {
                    $item['provider'] = $item['provider'] ?? $key;
                    return $item;
                })
            );
        }

        $source = $this->resolveSource($providerKey);

        $keywords = $this->keywordMapper->keywords($stock);

        $exclusions = $this->keywordMapper->exclusionKeywords($stock);
        $domainWhitelist = $this->domainList(env('NEWS_DOMAIN_WHITELIST', ''));
        $domainBlacklist = $this->domainList(env('NEWS_DOMAIN_BLACKLIST', ''));
        $threshold = (float) config('news.relevance_threshold', 0.35);
        $finalThreshold = (float) config('news.final_quality_threshold', 0.4);
        $this->deduper->reset();

        $scoredArticles = $rawArticles
            ->filter(fn ($raw) => $this->passesDomainAndExclusion($raw, $exclusions, $domainWhitelist, $domainBlacklist))
            ->map(function ($raw) use ($stock) {
                $score = $this->relevanceScoringService->score($stock, $raw, $raw['provider'] ?? null);
                return array_merge($raw, $score);
            })
            ->filter(function ($row) use ($threshold, $finalThreshold) {
                $lang = strtolower($row['detected_language'] ?? $row['language'] ?? '');
                if ($lang && ! in_array($lang, ['id', 'en'])) {
                    return false;
                }
                if (($row['relevance_score'] ?? 0) < $threshold) {
                    return false;
                }
                $finalScore = $row['final_quality_score'] ?? $row['relevance_score'] ?? 0;
                if ($finalScore < $finalThreshold) {
                    return false;
                }
                return true;
            })
            ->sortByDesc('final_quality_score')
            ->values();

        foreach ($scoredArticles as $rawArticle) {
            if ($this->deduper->shouldSkip($rawArticle)) {
                continue;
            }

            if (! $this->isRelevant($rawArticle, $keywords)) {
                continue;
            }

            $title = $rawArticle['title'] ?? 'Berita '.$stock->code;
            $slug = Str::slug($rawArticle['slug'] ?? $title) ?: Str::random(8);
            $summary = $rawArticle['summary'] ?? $title;
            $analysis = $this->analyzer->analyze($summary, [
                'title' => $title,
                'summary' => $summary,
                'body' => $rawArticle['full_text'] ?? $rawArticle['content_snippet'] ?? null,
                'language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
            ]);
            $sourceUrl = $rawArticle['source_url'] ?? null;

            // Pastikan slug unik jika sudah ada, tapi gunakan source_url sebagai key utama jika tersedia.
            if ($sourceUrl) {
                $match = ['source_url' => $sourceUrl];
            } else {
                if (NewsArticle::where('slug', $slug)->exists()) {
                    $slug .= '-'.Str::random(4);
                }
                $match = ['slug' => $slug];
            }

            NewsArticle::updateOrCreate($match, [
                'slug' => $slug,
                'stock_id' => $stock->id,
                'news_source_id' => $source?->id,
                'source_provider' => $rawArticle['provider'] ?? $providerKey,
                'source_weight' => $rawArticle['source_weight'] ?? null,
                'title' => $title,
                'source_url' => $sourceUrl ?? 'https://news.local/'.$slug,
                'published_at' => $rawArticle['published_at'] ?? Carbon::now(),
                'summary' => $summary,
                'content_snippet' => $rawArticle['content_snippet'] ?? null,
                'full_text' => $rawArticle['full_text'] ?? null,
                'sentiment_label' => $rawArticle['sentiment_label'] ?? $analysis['label'],
                'sentiment_score' => $rawArticle['sentiment_score'] ?? $analysis['score'],
                'sentiment_confidence' => $rawArticle['sentiment_confidence'] ?? $analysis['confidence'] ?? null,
                'sentiment_method' => $rawArticle['sentiment_method'] ?? $analysis['method'] ?? 'rule_based',
                'relevance_score' => $rawArticle['relevance_score'] ?? null,
                'relevance_band' => $rawArticle['relevance_band'] ?? null,
                'entity_match_score' => $rawArticle['entity_match_score'] ?? null,
                'market_context_score' => $rawArticle['market_context_score'] ?? null,
                'language_score' => $rawArticle['language_score'] ?? null,
                'final_quality_score' => $rawArticle['final_quality_score'] ?? null,
                'quality_band' => $rawArticle['quality_band'] ?? null,
                'matched_keywords' => $rawArticle['matched_keywords'] ?? null,
                'quality_flags' => $rawArticle['quality_flags'] ?? null,
                'sentiment_meta' => [
                    'matched_positive_terms' => $analysis['matched_positive_terms'] ?? [],
                    'matched_negative_terms' => $analysis['matched_negative_terms'] ?? [],
                    'reason_summary' => $analysis['reason_summary'] ?? null,
                ],
                'analyzed_at' => Carbon::now(),
                'language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
                'detected_language' => $rawArticle['detected_language'] ?? $rawArticle['language'] ?? 'id',
                'raw_payload' => $rawArticle['raw_payload'] ?? null,
                'fetched_at' => Carbon::now(),
            ]);
        }
    }

    protected function passesDomainAndExclusion(array $rawArticle, array $exclusions, array $domainWhitelist, array $domainBlacklist): bool
    {
        $domain = $this->extractDomain($rawArticle['source_url'] ?? null);
        if ($domain && in_array($domain, $domainBlacklist, true)) {
            return false;
        }
        if ($domainWhitelist && $domain && ! in_array($domain, $domainWhitelist, true)) {
            return false;
        }

        foreach ($exclusions as $ex) {
            $text = strtolower(implode(' ', array_filter([
                $rawArticle['title'] ?? '',
                $rawArticle['summary'] ?? '',
                $rawArticle['content_snippet'] ?? '',
                $rawArticle['full_text'] ?? '',
            ])));

            if ($ex && str_contains($text, strtolower($ex))) {
                return false;
            }
        }

        return true;
    }

    protected function isRelevant(array $rawArticle, array $keywords): bool
    {
        $text = strtolower(implode(' ', array_filter([
            $rawArticle['title'] ?? '',
            $rawArticle['summary'] ?? '',
            $rawArticle['content_snippet'] ?? '',
            $rawArticle['full_text'] ?? '',
        ])));

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
        return NewsSource::firstOrCreate(
            ['name' => Str::title($providerKey).' Provider'],
            [
                'type' => $providerKey,
                'is_active' => true,
                'config_json' => ['seeded' => true],
            ]
        );
    }
}
