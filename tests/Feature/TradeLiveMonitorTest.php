<?php

namespace Tests\Feature;

use App\Models\Trade;
use Tests\TestCase;

// Fase DA: Live Position Monitor -- /trades/live (halaman) + /trades/live-data (polling JSON).
class TradeLiveMonitorTest extends TestCase
{
    public function test_guest_cannot_view_live_monitor(): void
    {
        $this->get('/trades/live')->assertRedirect('/login');
    }

    public function test_live_page_renders_with_no_open_positions(): void
    {
        $user = $this->user();

        $this->actingAs($user)->get('/trades/live')
            ->assertOk()
            ->assertSee('Live Monitor');
    }

    public function test_live_data_endpoint_computes_trailing_stop_distance_and_status(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BUMI');

        // Entry 100, belum ada milestone_peak di tracker -> peak dianggap = entry (tidak ada
        // file open_positions.json di test env, readTrackerPeaks() harus gracefully return []).
        Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'BUMI',
            'status' => 'open',
            'entry_price' => 100,
            'entry_date' => now()->subDays(2),
            'strategy_label' => 'momentum',
            'lot_size' => 1000,
        ]);

        $response = $this->actingAs($user)->getJson('/trades/live-data');

        $response->assertOk();
        $positions = $response->json('positions');

        $this->assertCount(1, $positions);
        $this->assertSame('BUMI', $positions[0]['ticker']);
        $this->assertArrayHasKey('distance_to_sl_pct', $positions[0]);
        $this->assertArrayHasKey('trailing_sl', $positions[0]);
        $this->assertArrayHasKey('status', $positions[0]);
        $this->assertArrayHasKey('trading_days_held', $positions[0]);
        $this->assertArrayHasKey('days_remaining_to_target', $positions[0]);
        $this->assertGreaterThanOrEqual(1, $positions[0]['trading_days_held']);
    }

    public function test_live_data_only_returns_current_users_open_trades(): void
    {
        $owner = $this->user();
        $other = $this->user();
        $stock = $this->seedStock('DEWA');

        Trade::factory()->create([
            'user_id' => $other->id,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'status' => 'open',
            'entry_price' => 400,
            'entry_date' => now(),
        ]);

        $response = $this->actingAs($owner)->getJson('/trades/live-data');

        $response->assertOk();
        $this->assertCount(0, $response->json('positions'));
    }

    public function test_closed_trades_are_excluded_from_live_monitor(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BRPT');

        Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'BRPT',
            'status' => 'closed',
            'entry_price' => 1800,
            'exit_price' => 1900,
            'entry_date' => now()->subDays(5),
            'exit_date' => now(),
        ]);

        $response = $this->actingAs($user)->getJson('/trades/live-data');

        $response->assertOk();
        $this->assertCount(0, $response->json('positions'));
    }
}
