<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ReanalyzeSentimentCommandTest extends TestCase
{
    public function test_reanalyze_fills_indobert_and_rule_baseline_for_audit_page(): void
    {
        Config::set('sentiment.engine', 'python');
        Config::set('sentiment.python_endpoint', 'https://python.test/sentiment');
        Http::fake(['python.test/*' => Http::response([
            'label' => 'positive',
            'score' => 0.88,
            'confidence' => 0.93,
        ])]);

        $stock = $this->seedStock('BBCA');
        $article = $this->seedArticle($stock, [
            'summary' => 'BBCA laba bersih naik dan saham menguat.',
            'ml_sentiment_label' => null,
            'rule_sentiment_label' => null,
            'ml_rule_agree' => null,
        ]);

        $this->artisan('sentiment:reanalyze --stock=BBCA --limit=1')->assertExitCode(0);

        $article->refresh();

        $this->assertSame('python', $article->sentiment_method);
        $this->assertSame('positive', $article->ml_sentiment_label);
        $this->assertSame('positive', $article->rule_sentiment_label);
        $this->assertTrue((bool) $article->ml_rule_agree);
    }
}
