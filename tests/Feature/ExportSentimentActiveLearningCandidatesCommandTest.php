<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class ExportSentimentActiveLearningCandidatesCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_exports_unlabeled_positive_leaning_candidates_only(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $user = User::factory()->create();
        $output = storage_path('framework/testing/active_learning_candidates_'.uniqid().'.csv');

        $positiveCandidate = NewsArticle::factory()->for($stock)->create([
            'title' => 'Emiten cetak laba kuat',
            'ml_sentiment_label' => 'neutral',
            'rule_sentiment_label' => 'neutral',
            'ml_prob_positive' => 0.72,
            'ml_prob_neutral' => 0.20,
            'ml_prob_negative' => 0.08,
        ]);
        $uncertainCandidate = NewsArticle::factory()->for($stock)->create([
            'title' => 'Prospek membaik meski pasar hati-hati',
            'ml_sentiment_label' => 'neutral',
            'rule_sentiment_label' => 'neutral',
            'ml_prob_positive' => 0.34,
            'ml_prob_neutral' => 0.42,
            'ml_prob_negative' => 0.24,
        ]);
        $alreadyLabeled = NewsArticle::factory()->for($stock)->create([
            'ml_sentiment_label' => 'positive',
            'rule_sentiment_label' => 'positive',
            'ml_prob_positive' => 0.95,
            'ml_prob_neutral' => 0.03,
            'ml_prob_negative' => 0.02,
        ]);
        SentimentManualLabel::create(['news_article_id' => $alreadyLabeled->id, 'user_id' => $user->id, 'label' => 'positive']);
        NewsArticle::factory()->for($stock)->create([
            'title' => 'Tekanan biaya masih besar',
            'ml_sentiment_label' => 'negative',
            'rule_sentiment_label' => 'negative',
            'ml_prob_positive' => 0.05,
            'ml_prob_neutral' => 0.15,
            'ml_prob_negative' => 0.80,
        ]);

        $this->artisan('sentiment:export-active-learning-candidates', [
            '--output' => $this->relativeToBasePath($output),
            '--limit' => 10,
        ])->assertExitCode(0);

        $lines = array_map('str_getcsv', file($output, FILE_IGNORE_NEW_LINES));
        $this->assertContains('human_label', $lines[0]);
        $ids = array_column(array_slice($lines, 1), 0);
        $this->assertContains((string) $positiveCandidate->id, $ids);
        $this->assertContains((string) $uncertainCandidate->id, $ids);
        $this->assertNotContains((string) $alreadyLabeled->id, $ids);

        File::delete($output);
    }

    private function relativeToBasePath(string $path): string
    {
        return str_starts_with($path, base_path().DIRECTORY_SEPARATOR)
            ? substr($path, strlen(base_path()) + 1)
            : $path;
    }
}
