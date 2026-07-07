<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\News\SentimentAnalysisService;
use App\Services\Sentiment\SentimentAnalyzerInterface;
use App\Services\Sentiment\SentimentEngineManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SentimentAnalysisServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_rule_based_label_wins_as_final_when_ml_and_rule_disagree(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $article = NewsArticle::factory()->for($stock)->create([
            'title' => 'Laba BCA tumbuh dobel digit',
            'summary' => 'Laba BCA tumbuh dobel digit, perbankan tetap defensif',
        ]);

        $service = $this->serviceWithMlAnalyzer([
            'label' => 'neutral',
            'ml_label' => 'neutral',
            'rule_label' => null,
            'score' => 0.0,
            'confidence' => 0.6,
            'method' => 'python',
        ]);

        $service->analyzeAndUpdate($article);
        $article->refresh();

        // Rule-based lexicon should read "tumbuh" (grow) as positive, disagreeing with ML's neutral.
        $this->assertSame('positive', $article->rule_sentiment_label);
        $this->assertSame('neutral', $article->ml_sentiment_label);
        $this->assertFalse($article->ml_rule_agree);
        $this->assertSame('positive', $article->sentiment_label);
        $this->assertSame('rule_based_tiebreak', $article->sentiment_method);
    }

    public function test_ml_label_stays_final_when_ml_and_rule_agree(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $article = NewsArticle::factory()->for($stock)->create([
            'title' => 'BCA umumkan kebijakan baru',
            'summary' => 'BCA umumkan kebijakan operasional baru untuk cabang',
        ]);

        $service = $this->serviceWithMlAnalyzer([
            'label' => 'neutral',
            'ml_label' => 'neutral',
            'rule_label' => null,
            'score' => 0.0,
            'confidence' => 0.5,
            'method' => 'python',
        ]);

        $service->analyzeAndUpdate($article);
        $article->refresh();

        $this->assertSame('neutral', $article->rule_sentiment_label);
        $this->assertTrue($article->ml_rule_agree);
        $this->assertSame('neutral', $article->sentiment_label);
        $this->assertSame('python', $article->sentiment_method);
    }

    private function serviceWithMlAnalyzer(array $mlResult): SentimentAnalysisService
    {
        $analyzer = new class($mlResult) implements SentimentAnalyzerInterface {
            public function __construct(private array $result)
            {
            }

            public function analyze(string $text, array $context = []): array
            {
                return $this->result;
            }
        };

        $engineManager = new class($analyzer) extends SentimentEngineManager {
            public function __construct(private SentimentAnalyzerInterface $analyzer)
            {
            }

            public function getAnalyzer(): SentimentAnalyzerInterface
            {
                return $this->analyzer;
            }
        };

        return new SentimentAnalysisService($engineManager);
    }
}
