<?php

namespace Tests\Unit;

use App\Services\Sentiment\HybridSentimentAnalyzer;
use App\Services\Sentiment\PythonApiSentimentAnalyzer;
use App\Services\Sentiment\RuleBasedSentimentAnalyzer;
use Tests\TestCase;

class SentimentAnalyzerTest extends TestCase
{
    public function test_it_detects_positive_text_with_finance_lexicon(): void
    {
        $analyzer = new RuleBasedSentimentAnalyzer();
        $result = $analyzer->analyze('Laba tumbuh kuat dan ada dividen untuk pemegang saham', [
            'title' => 'Laba tumbuh kuat dan dividen',
        ]);

        $this->assertSame('positive', $result['label']);
        $this->assertGreaterThan(0, $result['score']);
        $this->assertNotEmpty($result['matched_positive_terms']);
    }

    public function test_it_detects_negative_text(): void
    {
        $analyzer = new RuleBasedSentimentAnalyzer();
        $result = $analyzer->analyze('Harga turun dan melemah dalam tekanan');

        $this->assertSame('negative', $result['label']);
        $this->assertLessThan(0, $result['score']);
    }

    public function test_negation_handling(): void
    {
        $analyzer = new RuleBasedSentimentAnalyzer();
        $result = $analyzer->analyze('Harga tidak naik dan belum membaik, masih ada tekanan margin');

        $this->assertSame('negative', $result['label']);
        $this->assertLessThan(0, $result['score']);
        $this->assertStringContainsString('negasi', $result['reason_summary']);
    }

    public function test_python_unavailable_is_explicit_and_not_hybrid_fallback(): void
    {
        config()->set('sentiment.engine', 'python');
        config()->set('sentiment.python_endpoint', null);

        $analyzer = new PythonApiSentimentAnalyzer();
        $result = $analyzer->analyze('Penurunan pendapatan dan suspensi perdagangan');

        $this->assertSame('neutral', $result['label']);
        $this->assertSame('python_unavailable', $result['method']);
        $this->assertSame('python_endpoint_missing', $result['python_status']);
    }

    public function test_hybrid_mode_no_longer_falls_back_to_rule_based(): void
    {
        config()->set('sentiment.engine', 'hybrid');
        config()->set('sentiment.python_endpoint', null);

        $analyzer = new HybridSentimentAnalyzer();
        $result = $analyzer->analyze('Penurunan pendapatan dan suspensi perdagangan');

        $this->assertSame('neutral', $result['label']);
        $this->assertSame('python_unavailable', $result['method']);
        $this->assertNotNull($result['confidence']);
    }
}
