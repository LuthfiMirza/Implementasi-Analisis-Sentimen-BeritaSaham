<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class AuditSentimentManualLabelsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_audit_flags_only_high_confidence_mismatches_without_changing_labels(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $user = User::factory()->create();
        $csv = storage_path('framework/testing/sentiment_audit_'.uniqid().'.csv');
        $txt = storage_path('framework/testing/sentiment_audit_'.uniqid().'.txt');

        $flagged = NewsArticle::factory()->for($stock)->create([
            'title' => 'Rekomendasi Saham BBCA dan BBRI Hari Ini',
            'ml_sentiment_label' => 'positive',
            'ml_prob_positive' => 0.95,
            'rule_sentiment_label' => 'neutral',
        ]);
        SentimentManualLabel::create([
            'news_article_id' => $flagged->id,
            'user_id' => $user->id,
            'label' => 'neutral',
            'sample_method' => 'legacy_hard_case',
        ]);

        $notFlagged = NewsArticle::factory()->for($stock)->create([
            'ml_sentiment_label' => 'positive',
            'ml_prob_positive' => 0.60,
        ]);
        SentimentManualLabel::create([
            'news_article_id' => $notFlagged->id,
            'user_id' => $user->id,
            'label' => 'negative',
            'sample_method' => 'legacy_hard_case',
        ]);

        $this->artisan('sentiment:audit-manual-labels', [
            '--csv' => $this->relativeToBasePath($csv),
            '--txt' => $this->relativeToBasePath($txt),
        ])->assertExitCode(0);

        $rows = array_map('str_getcsv', file($csv, FILE_IGNORE_NEW_LINES));
        $header = array_flip($rows[0]);
        $data = array_slice($rows, 1);
        $ids = array_column($data, $header['news_article_id']);
        $this->assertContains((string) $flagged->id, $ids);
        $this->assertContains('multi_emiten_recommendation', array_column($data, $header['article_type']));
        $this->assertNotContains((string) $notFlagged->id, $ids);
        $this->assertSame('neutral', SentimentManualLabel::where('news_article_id', $flagged->id)->value('label'));

        File::delete($csv);
        File::delete($txt);
    }

    private function relativeToBasePath(string $path): string
    {
        return str_starts_with($path, base_path().DIRECTORY_SEPARATOR)
            ? substr($path, strlen(base_path()) + 1)
            : $path;
    }
}
