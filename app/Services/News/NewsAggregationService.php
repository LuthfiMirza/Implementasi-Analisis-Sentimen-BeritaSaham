<?php

namespace App\Services\News;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use App\Services\News\ApiNewsFetcher;
use App\Services\News\FinnhubNewsFetcher;
use App\Services\News\GdeltFetcher;
use App\Services\News\ManualNewsFetcher;
use App\Services\News\MockNewsFetcher;
use App\Services\News\NewsApiFetcher;
use App\Services\News\RssLocalFetcher;
use App\Services\News\RssNewsFetcher;
use App\Services\News\StockKeywordMapper;
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
    ) {
        $this->sentimentEngineManager ??= new SentimentEngineManager();
        $this->analyzer ??= $this->sentimentEngineManager->getAnalyzer();
        $this->keywordMapper ??= new StockKeywordMapper();
        $this->fetchers = [
            'mock' => new MockNewsFetcher(),
            'manual' => new ManualNewsFetcher(),
            'rss' => new RssNewsFetcher(),
            'api' => new ApiNewsFetcher(),
            'finnhub' => new FinnhubNewsFetcher(),
            'newsapi' => new NewsApiFetcher($this->keywordMapper),
            'rss_local' => new RssLocalFetcher($this->keywordMapper),
            'gdelt' => new GdeltFetcher($this->keywordMapper),
        ];
    }

    public function fetchLatestArticles(Stock $stock, int $limit = 10)
    {
        return NewsArticle::with('source')
            ->where('stock_id', $stock->id)
            ->latest('published_at')
            ->limit($limit)
            ->get();
    }

    public function refreshFromProvider(Stock $stock, int $limit = 5): void
    {
        $providerKey = data_get(SystemSetting::where('key', 'news_provider')->first(), 'value.value')
            ?? config('services.news.provider', env('NEWS_PROVIDER', 'mock'));

        $providers = $providerKey === 'multi'
            ? ['newsapi', 'rss_local', 'gdelt', 'finnhub']
            : [$providerKey];

        $rawArticles = collect();
        foreach ($providers as $key) {
            $fetcher = $this->fetchers[$key] ?? null;
            if (! $fetcher) {
                continue;
            }
            $rawArticles = $rawArticles->merge($fetcher->fetchForStock($stock, $limit));
        }

        $source = $this->resolveSource($providerKey);

        $keywords = $this->keywordMapper->keywords($stock);

        $exclusions = $this->keywordMapper->exclusionKeywords($stock);
        $domainWhitelist = $this->domainList(env('NEWS_DOMAIN_WHITELIST', ''));
        $domainBlacklist = $this->domainList(env('NEWS_DOMAIN_BLACKLIST', ''));

        foreach ($rawArticles->unique('source_url') as $rawArticle) {
            if (! $this->isRelevant($rawArticle, $keywords, $exclusions, $domainWhitelist, $domainBlacklist)) {
                continue;
            }

            $title = $rawArticle['title'] ?? 'Berita '.$stock->code;
            $slug = Str::slug($rawArticle['slug'] ?? $title) ?: Str::random(8);
            $summary = $rawArticle['summary'] ?? $title;
            $analysis = $this->analyzer->analyze($summary, [
                'title' => $title,
                'summary' => $summary,
                'body' => $rawArticle['full_text'] ?? $rawArticle['content_snippet'] ?? null,
                'language' => $rawArticle['language'] ?? 'id',
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
                'sentiment_meta' => [
                    'matched_positive_terms' => $analysis['matched_positive_terms'] ?? [],
                    'matched_negative_terms' => $analysis['matched_negative_terms'] ?? [],
                    'reason_summary' => $analysis['reason_summary'] ?? null,
                ],
                'analyzed_at' => Carbon::now(),
                'language' => $rawArticle['language'] ?? 'id',
                'raw_payload' => $rawArticle['raw_payload'] ?? null,
                'fetched_at' => Carbon::now(),
            ]);
        }
    }

    protected function isRelevant(array $rawArticle, array $keywords, array $exclusions, array $domainWhitelist, array $domainBlacklist): bool
    {
        $text = strtolower(implode(' ', array_filter([
            $rawArticle['title'] ?? '',
            $rawArticle['summary'] ?? '',
            $rawArticle['content_snippet'] ?? '',
            $rawArticle['full_text'] ?? '',
        ])));

        $domain = $this->extractDomain($rawArticle['source_url'] ?? null);
        if ($domain && in_array($domain, $domainBlacklist, true)) {
            return false;
        }
        if ($domainWhitelist && $domain && ! in_array($domain, $domainWhitelist, true)) {
            return false;
        }

        foreach ($exclusions as $ex) {
            if ($ex && str_contains($text, strtolower($ex))) {
                return false;
            }
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
