<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\Trade;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AnalyzeTradeSentimentCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_reports_average_sentiment_for_wins_and_losses(): void
    {
        $user = User::factory()->create();
        $stock = Stock::factory()->create(['code' => 'DEWA']);

        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'published_at' => Carbon::parse('2026-01-03'),
            'sentiment_score' => 0.8,
            'sentiment_label' => 'positive',
        ]);
        NewsArticle::factory()->create([
            'stock_id' => $stock->id,
            'published_at' => Carbon::parse('2026-02-03'),
            'sentiment_score' => -0.6,
            'sentiment_label' => 'negative',
        ]);

        Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'entry_date' => Carbon::parse('2026-01-05'),
            'result' => 'hit_target_2',
            'pnl_percent' => 29.75,
            'status' => 'closed',
        ]);
        Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'entry_date' => Carbon::parse('2026-02-05'),
            'result' => 'stop_loss',
            'pnl_percent' => -3.25,
            'status' => 'closed',
        ]);

        $this->artisan('trades:analyze-sentiment', ['--user' => $user->id, '--window' => 5])
            ->expectsOutputToContain('Trade menang (TP): 1')
            ->expectsOutputToContain('Trade kalah (SL): 1')
            ->assertExitCode(0);
    }

    public function test_command_fails_gracefully_when_user_has_no_trades(): void
    {
        $user = User::factory()->create();

        $this->artisan('trades:analyze-sentiment', ['--user' => $user->id])
            ->assertExitCode(1);
    }
}
