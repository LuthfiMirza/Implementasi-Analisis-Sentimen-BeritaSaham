<?php

namespace Tests\Unit;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class NewsArticlesSchemaTest extends TestCase
{
    use RefreshDatabase;

    public function test_news_articles_has_sentiment_and_relevance_columns(): void
    {
        $this->assertTrue(Schema::hasColumns('news_articles', [
            'sentiment_confidence',
            'sentiment_method',
            'sentiment_meta',
            'analyzed_at',
            'relevance_score',
            'relevance_band',
            'source_provider',
            'source_weight',
            'matched_keywords',
        ]));
    }
}
