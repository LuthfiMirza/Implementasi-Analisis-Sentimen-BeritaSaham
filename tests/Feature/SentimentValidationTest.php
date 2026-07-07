<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use App\Models\Stock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SentimentValidationTest extends TestCase
{
    use RefreshDatabase;

    public function test_index_page_loads_with_disagreement_count(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        NewsArticle::factory()->for($stock)->create([
            'ml_sentiment_label' => 'neutral',
            'rule_sentiment_label' => 'positive',
            'ml_rule_agree' => false,
        ]);

        $this->actingAs($user)->get('/sentiment-validation')
            ->assertOk()
            ->assertSee('Label Manual: ML vs Rule-based');
    }

    public function test_next_returns_a_disagreement_article_not_yet_labeled_by_user(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $article = NewsArticle::factory()->for($stock)->create([
            'title' => 'Laba BCA tumbuh dobel digit',
            'ml_sentiment_label' => 'neutral',
            'rule_sentiment_label' => 'positive',
            'ml_rule_agree' => false,
        ]);
        NewsArticle::factory()->for($stock)->create(['ml_rule_agree' => true]);

        $response = $this->actingAs($user)->getJson('/sentiment-validation/next');

        $response->assertOk()
            ->assertJsonPath('done', false)
            ->assertJsonPath('article.id', $article->id)
            ->assertJsonPath('article.title', 'Laba BCA tumbuh dobel digit');
    }

    public function test_next_returns_done_when_all_disagreements_labeled(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $article = NewsArticle::factory()->for($stock)->create(['ml_rule_agree' => false]);
        SentimentManualLabel::create(['news_article_id' => $article->id, 'user_id' => $user->id, 'label' => 'positive']);

        $response = $this->actingAs($user)->getJson('/sentiment-validation/next');

        $response->assertOk()->assertJsonPath('done', true);
    }

    public function test_store_saves_label_and_is_idempotent_per_user(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);
        $article = NewsArticle::factory()->for($stock)->create(['ml_rule_agree' => false]);

        $this->actingAs($user)->postJson('/sentiment-validation/label', [
            'news_article_id' => $article->id,
            'label' => 'positive',
        ])->assertOk()->assertJsonPath('success', true);

        $this->assertDatabaseHas('sentiment_manual_labels', [
            'news_article_id' => $article->id,
            'user_id' => $user->id,
            'label' => 'positive',
        ]);
        $this->assertSame(1, SentimentManualLabel::count());

        // Re-submitting a different label for the same article updates rather than duplicates.
        $this->actingAs($user)->postJson('/sentiment-validation/label', [
            'news_article_id' => $article->id,
            'label' => 'negative',
        ])->assertOk();

        $this->assertSame(1, SentimentManualLabel::count());
        $this->assertDatabaseHas('sentiment_manual_labels', [
            'news_article_id' => $article->id,
            'label' => 'negative',
        ]);
    }

    public function test_summary_computes_agreement_rate_against_manual_labels(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'BBCA']);

        $mlCorrect = NewsArticle::factory()->for($stock)->create([
            'ml_sentiment_label' => 'positive',
            'rule_sentiment_label' => 'neutral',
            'ml_rule_agree' => false,
        ]);
        SentimentManualLabel::create(['news_article_id' => $mlCorrect->id, 'user_id' => $user->id, 'label' => 'positive']);

        $ruleCorrect = NewsArticle::factory()->for($stock)->create([
            'ml_sentiment_label' => 'neutral',
            'rule_sentiment_label' => 'negative',
            'ml_rule_agree' => false,
        ]);
        SentimentManualLabel::create(['news_article_id' => $ruleCorrect->id, 'user_id' => $user->id, 'label' => 'negative']);

        $response = $this->actingAs($user)->get('/sentiment-validation/summary');

        $response->assertOk()
            ->assertViewHas('total', 2)
            ->assertViewHas('mlAgreeRate', 50.0)
            ->assertViewHas('ruleAgreeRate', 50.0);
    }
}
