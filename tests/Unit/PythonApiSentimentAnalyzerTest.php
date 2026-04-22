<?php

namespace Tests\Unit;

use App\Services\Sentiment\PythonApiSentimentAnalyzer;
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

        $analyzer = new PythonApiSentimentAnalyzer();
        $result = $analyzer->analyze('Laba tumbuh pesat tahun ini', ['title' => 'Laba tumbuh']);

        $this->assertSame('python', $result['method']);
        $this->assertSame('positive', $result['label']);
        $this->assertEquals(0.82, $result['score']);
        $this->assertEquals(0.91, $result['confidence']);
        $this->assertNotEmpty($result['matched_positive_terms']);
        $this->assertSame('available', $result['python_status']);
        $this->assertNull($result['rule_label']);
    }

    public function test_invalid_payload_returns_explicit_python_unavailable_marker(): void
    {
        config()->set('sentiment.python_endpoint', 'http://python.test/sentiment');
        Http::fake([
            'http://python.test/sentiment' => Http::response(['score' => 0.5], 200),
        ]);

        $analyzer = new PythonApiSentimentAnalyzer();
        $result = $analyzer->analyze('Berita tanpa label');

        $this->assertSame('python_unavailable', $result['method']);
        $this->assertSame('neutral', $result['label']);
        $this->assertSame(0.0, $result['score']);
        $this->assertSame('python_invalid_payload', $result['python_status']);
        $this->assertNull($result['rule_label']);
    }

    public function test_http_error_does_not_fall_back_to_rule_based(): void
    {
        config()->set('sentiment.python_endpoint', 'http://python.test/sentiment');
        Http::fake([
            'http://python.test/sentiment' => Http::response(null, 500),
        ]);

        $analyzer = new PythonApiSentimentAnalyzer();
        $result = $analyzer->analyze('Rugi bersih dan gagal bayar');

        $this->assertSame('python_unavailable', $result['method']);
        $this->assertSame('neutral', $result['label']);
        $this->assertSame('python_http_error', $result['python_status']);
        $this->assertStringContainsString('HTTP 500', $result['reason_summary']);
    }

    public function test_missing_endpoint_returns_explicit_unavailable_marker(): void
    {
        config()->set('sentiment.python_endpoint', null);

        $analyzer = new PythonApiSentimentAnalyzer();
        $result = $analyzer->analyze('Laba emiten meningkat');

        $this->assertSame('python_unavailable', $result['method']);
        $this->assertSame('python_endpoint_missing', $result['python_status']);
        $this->assertSame('neutral', $result['label']);
    }
}
