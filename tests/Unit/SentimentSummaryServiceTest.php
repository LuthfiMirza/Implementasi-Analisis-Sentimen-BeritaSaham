<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Services\Sentiment\SentimentSummaryService;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Tests\TestCase;

class SentimentSummaryServiceTest extends TestCase
{
    public function test_summary_splits_available_and_unavailable_sentiment(): void
    {
        $service = new SentimentSummaryService();
        $articles = new Collection([
            new NewsArticle([
                'sentiment_label' => 'positive',
                'sentiment_score' => 0.7,
                'sentiment_method' => 'python',
                'published_at' => Carbon::parse('2024-01-01'),
            ]),
            new NewsArticle([
                'sentiment_label' => 'neutral',
                'sentiment_score' => 0.0,
                'sentiment_method' => 'python_unavailable',
                'published_at' => Carbon::parse('2024-01-01'),
            ]),
        ]);

        $summary = $service->summarize($articles);

        $this->assertSame(1, $summary['total']);
        $this->assertSame(2, $summary['article_total']);
        $this->assertSame(1, $summary['positive']);
        $this->assertSame(0, $summary['neutral']);
        $this->assertSame(1, $summary['sentiment_available_count']);
        $this->assertSame(1, $summary['sentiment_unavailable_count']);
        $this->assertEquals(0.7, $summary['average_score']);
    }

    public function test_generate_insight_reports_unavailable_state_honestly(): void
    {
        $service = new SentimentSummaryService();

        $insight = $service->generateInsight('BBCA', [
            'average_score' => 0.0,
            'sentiment_available_count' => 0,
            'sentiment_unavailable_count' => 2,
        ]);

        $this->assertStringContainsString('belum tersedia dari IndoBERT', $insight);
        $this->assertStringContainsString('2 artikel masih berstatus unavailable', $insight);
    }
}
