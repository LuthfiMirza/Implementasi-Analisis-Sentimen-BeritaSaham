<?php

namespace Tests\Unit;

use App\Services\Sentiment\HybridSentimentAnalyzer;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class SentimentAnalyzerTest extends TestCase
{
    public function test_rule_based_returns_positive_neutral_and_negative_for_financial_text(): void
    {
        $analyzer = new RuleBasedSentimentAnalyzer();

        $positive = $analyzer->analyze('BBCA laba bersih naik dan saham menguat.');
        $neutral = $analyzer->analyze('BBCA menggelar RUPS dan agenda operasional.');
        $negative = $analyzer->analyze('BBCA laba turun dan saham melemah.');

        // Clear Indonesian finance terms must map to the expected polarity buckets.
        $this->assertSame('positive', $positive['label']);
        $this->assertSame('neutral', $neutral['label']);
        $this->assertSame('negative', $negative['label']);
    }

    public function test_python_engine_unreachable_falls_back_without_exception_shape(): void
    {
        Config::set('sentiment.engine', 'python');
        Config::set('sentiment.python_endpoint', 'https://python.test/predict');
        Http::fake(['python.test/*' => Http::response(null, 503)]);

        $result = (new HybridSentimentAnalyzer())->analyze('BBCA laba naik signifikan.');

        // External ML outages must not crash article ingestion.
        $this->assertContains($result['method'], ['fallback', 'rule_based', 'hybrid', 'python_unavailable']);
        $this->assertArrayHasKey('label', $result);
    }

    public function test_hybrid_mode_uses_valid_python_json(): void
    {
        Config::set('sentiment.engine', 'python');
        Config::set('sentiment.python_endpoint', 'https://python.test/predict');
        Http::fake(['python.test/*' => Http::response([
            'label' => 'positive',
            'score' => 0.82,
            'confidence' => 0.91,
            'matched_positive_terms' => ['laba naik'],
            'matched_negative_terms' => [],
        ])]);

        $result = (new HybridSentimentAnalyzer())->analyze('BBCA laba naik.');

        // Valid ML payloads should be preserved for auditability.
        $this->assertSame('positive', $result['label']);
        $this->assertSame(0.82, $result['score']);
        $this->assertSame(0.91, $result['confidence']);
    }

    public function test_result_contract_contains_confidence_terms_and_method(): void
    {
        Config::set('sentiment.engine', 'rule_based');

        $result = (new HybridSentimentAnalyzer())->analyze('BBCA laba naik tetapi risiko pasar masih ada.');

        // Consumers store these fields directly on news_articles.
        $this->assertGreaterThanOrEqual(0, $result['confidence']);
        $this->assertLessThanOrEqual(1, $result['confidence']);
        $this->assertIsArray($result['matched_positive_terms']);
        $this->assertIsArray($result['matched_negative_terms']);
        $this->assertContains($result['method'], ['rule_based', 'python_api', 'hybrid', 'fallback']);
    }

    public function test_empty_and_foreign_text_are_handled_gracefully(): void
    {
        $analyzer = new RuleBasedSentimentAnalyzer();

        $empty = $analyzer->analyze('');
        $foreign = $analyzer->analyze('これは市場ニュースではありません');

        // Empty or unsupported language should not throw or create strong false signals.
        $this->assertSame('neutral', $empty['label']);
        $this->assertSame('neutral', $foreign['label']);
        $this->assertLessThanOrEqual(0.6, $foreign['confidence']);
    }
}
