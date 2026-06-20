<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use App\Services\News\NewsFetcherInterface;
use App\Services\Sentiment\SentimentAnalyzerInterface;
use Carbon\Carbon;
use ReflectionClass;
use Tests\TestCase;

class NewsAggregationServiceTest extends TestCase
{
    public function test_deduplication_same_source_url_is_not_saved_twice(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, ['source_url' => 'https://kontan.test/bbca-laba?utm=a']),
            $this->rawArticle($stock, ['source_url' => 'https://kontan.test/bbca-laba?utm=b']),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // URL normalization should prevent duplicate records from provider tracking params.
        $this->assertSame(1, $stats['saved']);
        $this->assertSame(1, $stats['skipped_dedup']);
        $this->assertSame(1, NewsArticle::count());
    }

    public function test_deduplication_same_normalized_title_domain_and_date_is_rejected(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, ['title' => 'BBCA laba bersih naik dan saham menguat', 'source_url' => 'https://kontan.test/a']),
            $this->rawArticle($stock, ['title' => 'BBCA laba bersih naik dan saham menguat!!!', 'source_url' => 'https://kontan.test/b']),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // Same news item should not enter sentiment statistics twice.
        $this->assertSame(1, $stats['saved']);
        $this->assertSame(1, $stats['skipped_dedup']);
    }

    public function test_relevance_filter_drops_article_without_ticker_keyword(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, [
                'title' => 'IHSG bergerak datar dan pasar menunggu data',
                'summary' => 'Pasar menunggu data ekonomi tanpa menyebut emiten target.',
                'direct_keyword_hits' => [],
            ]),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // Stock-specific dashboards must not be polluted by unrelated market news.
        $this->assertSame(0, $stats['saved']);
        $this->assertSame(1, $stats['dropped_irrelevant']);
    }

    public function test_exclusion_keyword_article_is_dropped(): void
    {
        $stock = $this->seedStock('GOTO', ['company_name' => 'GoTo Gojek Tokopedia Tbk']);
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, ['title' => 'Wisata goto islands makin populer', 'summary' => 'goto islands bukan emiten']),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // Ambiguous ticker words require exclusion filters to avoid false entity matches.
        $this->assertSame(0, $stats['saved']);
        $this->assertGreaterThanOrEqual(1, $stats['dropped_exclusion'] + $stats['dropped_irrelevant']);
    }

    public function test_quality_score_below_threshold_is_not_saved(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, ['final_quality_score' => 0.1]),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // Low-quality content should not affect thesis analytics.
        $this->assertSame(0, $stats['saved']);
        $this->assertSame(1, $stats['dropped_quality']);
    }

    public function test_language_filter_rejects_japanese_article(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, ['language' => 'ja', 'detected_language' => 'ja']),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // Non-ID/EN articles should not be scored by an Indonesian finance lexicon.
        $this->assertSame(0, $stats['saved']);
        $this->assertSame(1, $stats['dropped_language']);
    }

    public function test_ojk_articles_are_saved_globally_with_ojk_provider(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, [
                'provider' => 'ojk_rss',
                'issuer_specificity' => 'macro_regulatory',
                'title' => 'OJK umumkan kebijakan pasar modal untuk investor',
                'direct_keyword_hits' => [],
            ]),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);

        // OJK macro news is global context, not company-specific news.
        $this->assertSame(1, $stats['saved']);
        $this->assertDatabaseHas('news_articles', ['stock_id' => null, 'source_provider' => 'ojk_rss']);
    }

    public function test_multi_provider_mode_calls_all_configured_providers(): void
    {
        config([
            'services.news.provider' => 'multi',
            'news.multi_providers' => ['fake_a', 'fake_b'],
            'news.preferred_providers.BBCA' => null,
        ]);
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithProviderMap([
            'fake_a' => [$this->rawArticle($stock, ['source_url' => 'https://a.test/bbca'])],
            'fake_b' => [$this->rawArticle($stock, [
                'title' => 'BBCA dividen jumbo dan saham tetap positif',
                'summary' => 'BBCA membagikan dividen jumbo untuk investor.',
                'source_url' => 'https://b.test/bbca',
            ])],
        ]);

        $stats = $service->refreshFromProvider($stock, 10);

        // Multi mode must aggregate every configured source for provider resilience.
        $this->assertSame(2, $stats['raw']);
        $this->assertSame(2, $stats['saved']);
        $this->assertSame(1, $stats['by_provider']['fake_a']);
        $this->assertSame(1, $stats['by_provider']['fake_b']);
    }

    public function test_sentiment_is_auto_analyzed_after_save(): void
    {
        $stock = $this->seedStock('BBCA');
        $service = $this->serviceWithArticles([$this->rawArticle($stock)]);

        $service->refreshFromProvider($stock, 10, ['fake']);
        $article = NewsArticle::firstOrFail();

        // Saved rows must be analytics-ready immediately after ingestion.
        $this->assertSame('positive', $article->sentiment_label);
        $this->assertSame(0.75, (float) $article->sentiment_score);
        $this->assertNotNull($article->analyzed_at);
    }

    public function test_very_long_title_is_saved_with_database_safe_slug_without_crashing(): void
    {
        $stock = $this->seedStock('GOTO', ['company_name' => 'GoTo Gojek Tokopedia Tbk']);
        $longTitle = 'GOTO GoTo Gojek Tokopedia mencatat penguatan saham dan ekspansi ekosistem digital '.str_repeat('dengan pertumbuhan pendapatan dan efisiensi operasional berkelanjutan ', 8);
        $service = $this->serviceWithArticles([
            $this->rawArticle($stock, [
                'title' => $longTitle,
                'summary' => $longTitle,
                'source_url' => 'https://kontan.test/goto-long-title',
                'direct_keyword_hits' => ['GOTO'],
            ]),
        ]);

        $stats = $service->refreshFromProvider($stock, 10, ['fake']);
        $article = NewsArticle::firstOrFail();

        $this->assertSame(1, $stats['saved']);
        $this->assertSame(0, $stats['failed']);
        $this->assertLessThanOrEqual(255, mb_strlen($article->title));
        $this->assertLessThanOrEqual(220, mb_strlen($article->slug));
        $this->assertStringContainsString(substr(sha1($longTitle), 0, 10), $article->slug);
    }

    private function rawArticle(Stock $stock, array $overrides = []): array
    {
        return array_merge([
            'provider' => 'fake',
            'title' => "{$stock->code} laba bersih naik dan saham menguat",
            'summary' => "{$stock->code} mencatat laba bersih naik.",
            'source_url' => 'https://kontan.test/'.strtolower($stock->code).'-'.uniqid(),
            'published_at' => Carbon::parse('2026-04-20 09:00:00'),
            'language' => 'id',
            'detected_language' => 'id',
            'relevance_score' => 0.9,
            'entity_match_score' => 1.0,
            'market_context_score' => 1.0,
            'language_score' => 1.0,
            'final_quality_score' => 0.9,
            'issuer_specificity' => 'direct',
            'direct_keyword_hits' => [$stock->code],
            'competing_keyword_hits' => [],
            'skip_relevance_rescore' => true,
        ], $overrides);
    }

    private function serviceWithArticles(array $articles): NewsAggregationService
    {
        return $this->serviceWithProviderMap(['fake' => $articles]);
    }

    private function serviceWithProviderMap(array $map): NewsAggregationService
    {
        $analyzer = new class implements SentimentAnalyzerInterface {
            public function analyze(string $text, array $context = []): array
            {
                return [
                    'label' => 'positive',
                    'score' => 0.75,
                    'confidence' => 0.8,
                    'method' => 'rule_based',
                    'matched_positive_terms' => ['laba naik'],
                    'matched_negative_terms' => [],
                ];
            }
        };
        $service = new NewsAggregationService($analyzer);
        $fetchers = [];

        foreach ($map as $key => $articles) {
            $fetchers[$key] = new class($articles) implements NewsFetcherInterface {
                public function __construct(private array $articles) {}
                public function fetchForStock(Stock $stock, int $limit = 10): array
                {
                    return array_slice($this->articles, 0, $limit);
                }
            };
        }

        $ref = new ReflectionClass($service);
        $property = $ref->getProperty('fetchers');
        $property->setAccessible(true);
        $property->setValue($service, $fetchers);

        return $service;
    }
}
