<?php

namespace Tests\Feature;

use App\Models\Trade;
use Tests\TestCase;

class TradeJournalTest extends TestCase
{
    public function test_authenticated_user_can_create_trade_entry(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BBCA');

        $response = $this->actingAs($user)->post('/trades', [
            'stock_id' => $stock->id,
            'entry_price' => 1000,
            'stop_loss' => 950,
            'target_1' => 1100,
            'target_2' => 1200,
            'lot_size' => 100,
            'entry_date' => '2026-04-30',
            'signal_quality' => 'A',
        ]);

        // Trade entries must be scoped to the authenticated user.
        $response->assertRedirect('/trades');
        $this->assertDatabaseHas('trades', ['user_id' => $user->id, 'stock_id' => $stock->id, 'status' => 'open']);
    }

    public function test_guest_cannot_create_trade_entry(): void
    {
        $stock = $this->seedStock('BBCA');

        // Trade creation changes account data and must require auth.
        $this->post('/trades', ['stock_id' => $stock->id])->assertRedirect('/login');
    }

    public function test_closing_trade_stores_exit_price_and_pnl(): void
    {
        $user = $this->user();
        $trade = Trade::factory()->create(['user_id' => $user->id, 'entry_price' => 1000, 'stop_loss' => 950, 'lot_size' => 100]);

        $this->actingAs($user)->post("/trades/{$trade->id}/close", [
            'exit_price' => 1100,
            'result' => 'hit_target_1',
        ])->assertRedirect('/trades');

        // P&L fields are core audit evidence for paper trading decisions.
        $this->assertDatabaseHas('trades', [
            'id' => $trade->id,
            'status' => 'closed',
            'exit_price' => 1100,
            'pnl_total' => 10000,
        ]);
    }

    public function test_listing_returns_only_current_users_trades(): void
    {
        $user = $this->user();
        $other = $this->user();
        $stock = $this->seedStock('BBCA');
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $stock->id, 'notes' => 'visible-trade']);
        Trade::factory()->create(['user_id' => $other->id, 'stock_id' => $stock->id, 'notes' => 'hidden-trade']);

        $response = $this->actingAs($user)->get('/trades');

        // Cross-user trade leakage would be a direct privacy defect.
        $response->assertOk()->assertViewHas('trades', function ($trades) use ($user, $other) {
            return $trades->pluck('user_id')->contains($user->id)
                && ! $trades->pluck('user_id')->contains($other->id);
        });
    }
}
