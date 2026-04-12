<?php

namespace Tests\Unit;

use App\Services\Sentiment\PythonApiSentimentAnalyzer;
use App\Services\Sentiment\SentimentAnalyzerInterface;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class PythonApiSentimentAnalyzerTest extends TestCase
{
    public function test_python_response_used_when_valid(): void
    {
        config()->set('sentiment.python_endpoint', 'http://python.test/sentiment');

        Http::fake([
            'http://python.test/sentiment' => Http::response([
                'label' => 'positive',
                'score' => 0.82,
                'confidence' => 0.91,
                'matched_positive_terms' => ['laba tumbuh'],
                'reason_summary' => 'Model yakin',
            ], 200),
        ]);

        $fallback = new class implements SentimentAnalyzerInterface {
            public function analyze(string $text, array $context = []): array
            {
                return ['label' => 'neutral', 'score' => 0.0, 'confidence' => 0.5, 'method' => 'rule_based'];
            }
        };

        $analyzer = new PythonApiSentimentAnalyzer($fallback);
        $result = $analyzer->analyze('Laba tumbuh pesat tahun ini', ['title' => 'Laba tumbuh']);

        $this->assertSame('python', $result['method']);
        $this->assertSame('positive', $result['label']);
        $this->assertEquals(0.82, $result['score']);
        $this->assertEquals(0.91, $result['confidence']);
        $this->assertNotEmpty($result['matched_positive_terms']);
    }

    public function test_invalid_payload_falls_back_to_rule_based(): void
    {
        config()->set('sentiment.python_endpoint', 'http://python.test/sentiment');
        Http::fake([
            'http://python.test/sentiment' => Http::response(['score' => 0.5], 200),
        ]);

        $fallback = new class implements SentimentAnalyzerInterface {
            public function analyze(string $text, array $context = []): array
            {
                return ['label' => 'neutral', 'score' => 0.1, 'confidence' => 0.55, 'method' => 'rule_based'];
            }
        };

        $analyzer = new PythonApiSentimentAnalyzer($fallback);
        $result = $analyzer->analyze('Berita tanpa label');

        $this->assertSame('rule_based', $result['method']);
        $this->assertSame('neutral', $result['label']);
    }

    public function test_http_error_triggers_fallback(): void
    {
        config()->set('sentiment.python_endpoint', 'http://python.test/sentiment');
        Http::fake([
            'http://python.test/sentiment' => Http::response(null, 500),
        ]);

        $fallback = new class implements SentimentAnalyzerInterface {
            public function analyze(string $text, array $context = []): array
            {
                return ['label' => 'negative', 'score' => -0.4, 'confidence' => 0.6, 'method' => 'rule_based'];
            }
        };

        $analyzer = new PythonApiSentimentAnalyzer($fallback);
        $result = $analyzer->analyze('Rugi bersih dan gagal bayar');

        $this->assertSame('rule_based', $result['method']);
        $this->assertSame('negative', $result['label']);
    }
}
