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
            'lot' => 5,
            'entry_date' => '2026-04-30',
            'signal_quality' => 'A',
        ]);

        // Trade entries must be scoped to the authenticated user.
        $response->assertRedirect('/trades');
        $this->assertDatabaseHas('trades', ['user_id' => $user->id, 'stock_id' => $stock->id, 'status' => 'open']);
    }

    public function test_lot_input_is_converted_to_lembar_at_100_per_lot(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BBCA');

        $this->actingAs($user)->post('/trades', [
            'stock_id' => $stock->id,
            'entry_price' => 1000,
            'stop_loss' => 950,
            'target_1' => 1100,
            'lot' => 5,
            'entry_date' => '2026-04-30',
        ])->assertRedirect('/trades');

        // Konvensi IDX: 1 Lot = 100 lembar -- form minta Lot (kebiasaan broker), kolom lot_size
        // di DB tetap menyimpan lembar karena itu yang dipakai perhitungan PnL.
        $this->assertDatabaseHas('trades', [
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'lot_size' => 500,
            'position_value' => 500000,
        ]);
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

    public function test_win_rate_counts_profitable_manual_close_trades_as_wins(): void
    {
        $user = $this->user();

        // manual_close (exit berbasis waktu, mis. aturan drawdown-bounce) dengan PnL positif
        // HARUS terhitung sebagai "menang" walau result-nya bukan hit_target_1/2 -- sebelumnya
        // trade seperti ini hilang sama sekali dari Win Rate.
        //
        // Fase CA: kartu ringkasan resmi cuma menghitung strategy_label='gabungan' -- wajib
        // diisi eksplisit di sini, factory tidak set default (lihat TradeController::index()).
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'result' => 'manual_close', 'pnl_total' => 500000, 'pnl_percent' => 10,
            'strategy_label' => 'gabungan',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'result' => 'manual_close', 'pnl_total' => -200000, 'pnl_percent' => -5,
            'strategy_label' => 'gabungan',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'result' => 'hit_target_2', 'pnl_total' => 300000, 'pnl_percent' => 8,
            'strategy_label' => 'gabungan',
        ]);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk()->assertViewHas('stats', function ($stats) {
            // 2 menang (1 manual_close positif + 1 hit_target_2), 1 kalah (manual_close negatif).
            return $stats['win'] === 2 && $stats['loss'] === 1
                && abs($stats['win_rate'] - 66.7) < 0.1;
        });
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

    public function test_episode_count_groups_trades_within_15_days_per_ticker(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BUMI');

        // 3 trade BUMI berdekatan (jeda <=15 hari) -- HARUS terhitung 1 episode, bukan 3.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-06-01', 'pnl_total' => 100000, 'strategy_label' => 'gabungan',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-06-08', 'pnl_total' => 50000, 'strategy_label' => 'gabungan',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-06-15', 'pnl_total' => -20000, 'strategy_label' => 'gabungan',
        ]);

        // Trade BUMI ke-4, jeda 20 hari dari yang terakhir -- episode BARU.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-07-05', 'pnl_total' => 300000, 'strategy_label' => 'gabungan',
        ]);

        // Ticker BEDA (DEWA) di tanggal yang sama dengan trade pertama BUMI -- episode terpisah,
        // TIDAK boleh ikut tergabung walau tanggalnya berdekatan (episode dikelompokkan per ticker).
        $dewa = $this->seedStock('DEWA');
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $dewa->id, 'ticker' => 'DEWA',
            'entry_date' => '2026-06-02', 'pnl_total' => 75000, 'strategy_label' => 'gabungan',
        ]);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk()->assertViewHas('stats', function ($stats) {
            // 5 trade mentah -> 3 episode: [BUMI 1-8 Jun], [BUMI 15 Jun+5Jul? -- cek jeda], [DEWA].
            // Jeda BUMI trade-3 (15 Jun) ke trade-4 (5 Jul) = 20 hari > 15 -> episode baru.
            // Jadi: episode 1 = {1 Jun, 8 Jun, 15 Jun}, episode 2 = {5 Jul}, episode 3 = {DEWA 2 Jun}.
            return $stats['episode_count'] === 3;
        });
    }
}
