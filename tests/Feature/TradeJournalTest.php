<?php

namespace Tests\Feature;

use App\Models\Trade;
use Tests\TestCase;

class TradeJournalTest extends TestCase
{
    // Fase DM: bug ditemukan user (1 Sep 2026) -- label "Masuk" di kartu posisi terbuka dulu
    // pakai created_at (kapan baris DB dibuat), bukan entry_date (tanggal trading sinyal itu
    // berlaku). Job harian detect-drawdown-bounce-signal sempat kelewat 31 Agu 2026 (Mac tidur),
    // baru catch-up 1 Sep -- sinyal MOMENTUM DSSA entry_date=31 Agu tapi created_at=1 Sep 15:18,
    // bikin kartu terlihat seolah baru masuk hari ini dengan harga "salah" (padahal harga
    // closing 31 Agu yang valid, cuma telat tersinkron). Test ini reproduksi persis kasus itu.
    public function test_open_position_card_shows_entry_date_not_created_at(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('DSSA');

        $trade = Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'DSSA',
            'strategy_label' => 'momentum',
            'status' => 'open',
            'entry_price' => 1110,
            'entry_date' => '2026-08-31',
            'trade_date' => '2026-08-31',
        ]);
        // created_at di-set belakangan (simulasi job yang telat catch-up) -- Eloquent otomatis
        // isi created_at saat create(), jadi di-override manual lewat query builder (bypass
        // timestamps otomatis) supaya persis meniru kondisi produksi.
        Trade::where('id', $trade->id)->update(['created_at' => '2026-09-01 15:18:21']);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk();
        $response->assertSee('Masuk 31 Aug 2026', false);
        $response->assertDontSee('Masuk 01 Sep 2026', false);
        // Transparansi: kartu tetap menyebut kapan sebenarnya tersinkron, supaya user tidak
        // bingung kalau nemu harga "closing" tapi baris barusan muncul di halaman.
        $response->assertSee('tersinkron 01 Sep', false);
    }

    public function test_open_position_card_hides_sync_note_when_same_day(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BBCA');

        Trade::factory()->create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'BBCA',
            'status' => 'open',
            'entry_date' => now()->toDateString(),
            'trade_date' => now()->toDateString(),
        ]);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk();
        $response->assertDontSee('tersinkron', false);
    }

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

        $response = $this->actingAs($user)->get('/trades/laporan');

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

        $response = $this->actingAs($user)->get('/trades/laporan');

        $response->assertOk()->assertViewHas('stats', function ($stats) {
            // 5 trade mentah -> 3 episode: [BUMI 1-8 Jun], [BUMI 15 Jun+5Jul? -- cek jeda], [DEWA].
            // Jeda BUMI trade-3 (15 Jun) ke trade-4 (5 Jul) = 20 hari > 15 -> episode baru.
            // Jadi: episode 1 = {1 Jun, 8 Jun, 15 Jun}, episode 2 = {5 Jul}, episode 3 = {DEWA 2 Jun}.
            return $stats['episode_count'] === 3;
        });
    }

    public function test_monthly_episode_breakdown_groups_by_episode_start_month(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('BUMI');

        // Episode 1: mulai Juni, trade lanjutan (jeda <=15 hari) nyeberang ke Juli -- HARUS
        // terhitung 1 episode di bulan MULAI-nya (Juni), bukan tercatat dobel di Juni & Juli.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-06-25', 'pnl_total' => 100000, 'strategy_label' => 'gabungan',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-07-05', 'pnl_total' => 50000, 'strategy_label' => 'gabungan',
        ]);

        // Episode 2: murni di Agustus, jeda 25 hari dari episode 1 -- episode terpisah.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-08-01', 'pnl_total' => -30000, 'strategy_label' => 'gabungan',
        ]);

        $response = $this->actingAs($user)->get('/trades/laporan');

        $response->assertOk()->assertViewHas('monthlyBreakdown', function ($breakdown) {
            $byMonth = collect($breakdown)->keyBy('month');
            // Juni: 1 episode (2 trade mentah, termasuk yang entry-nya di Juli tapi episode
            // yang sama) -- Juli TIDAK boleh muncul sebagai bulan terpisah untuk episode ini.
            $juneOk = ($byMonth['2026-06']['episode_count'] ?? null) === 1
                && ($byMonth['2026-06']['trade_count'] ?? null) === 2;
            $julyAbsent = ! $byMonth->has('2026-07');
            $augustOk = ($byMonth['2026-08']['episode_count'] ?? null) === 1
                && ($byMonth['2026-08']['trade_count'] ?? null) === 1;

            return $juneOk && $julyAbsent && $augustOk;
        });
    }

    public function test_strategy_breakdown_also_reports_episode_independence(): void
    {
        $user = $this->user();
        $stock = $this->seedStock('SMGR');

        // 3 trade SMGR berdekatan (jeda <=15 hari) di strategi legacy_stock_only -- HARUS
        // terhitung 1 episode, sama seperti GABUNGAN, bukan cuma dihitung raw count.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'SMGR',
            'entry_date' => '2026-03-01', 'pnl_total' => 40000, 'strategy_label' => 'legacy_stock_only',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'SMGR',
            'entry_date' => '2026-03-05', 'pnl_total' => -10000, 'strategy_label' => 'legacy_stock_only',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $stock->id, 'ticker' => 'SMGR',
            'entry_date' => '2026-03-10', 'pnl_total' => 25000, 'strategy_label' => 'legacy_stock_only',
        ]);

        $response = $this->actingAs($user)->get('/trades/laporan');

        $response->assertOk()->assertViewHas('strategyBreakdown', function ($breakdown) {
            $legacy = collect($breakdown)->firstWhere('key', 'legacy_stock_only');

            return $legacy !== null
                && $legacy['closed'] === 3
                && $legacy['episode_count'] === 1;
        });
    }

    public function test_momentum_episode_independence_computes_correctly_once_trades_close(): void
    {
        // Momentum baru live 3 hari (Fase BL) -- 0 trade closed per hari ini, jadi tidak ada data
        // nyata untuk dicek. Tes ini mengunci PERILAKU kodenya sekarang (bukan nunggu data asli
        // ada), supaya kalau nanti posisi momentum BUMI/DEWA/BRPT mulai ditutup, angka episode-nya
        // sudah terjamin benar sejak awal -- sama protokol dgn legacy_stock_only di atas.
        $user = $this->user();
        $bumi = $this->seedStock('BUMI');
        $brpt = $this->seedStock('BRPT');

        // BUMI: 2 trade berdekatan (jeda <=15 hari) -- 1 episode.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $bumi->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-09-01', 'pnl_total' => 60000, 'strategy_label' => 'momentum',
        ]);
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $bumi->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-09-10', 'pnl_total' => -15000, 'strategy_label' => 'momentum',
        ]);

        // BRPT: 1 trade, jeda jauh dari BUMI (ticker beda, tidak relevan) -- episode sendiri.
        Trade::factory()->closeState()->create([
            'user_id' => $user->id, 'stock_id' => $brpt->id, 'ticker' => 'BRPT',
            'entry_date' => '2026-09-15', 'pnl_total' => 90000, 'strategy_label' => 'momentum',
        ]);

        // 1 posisi momentum MASIH TERBUKA -- tidak boleh ikut terhitung ke episode (episode cuma
        // dari trade CLOSED), tapi harus tetap muncul di kolom 'open'.
        Trade::factory()->create([
            'user_id' => $user->id, 'stock_id' => $bumi->id, 'ticker' => 'BUMI',
            'entry_date' => '2026-09-20', 'status' => 'open', 'strategy_label' => 'momentum',
        ]);

        $response = $this->actingAs($user)->get('/trades/laporan');

        $response->assertOk()->assertViewHas('strategyBreakdown', function ($breakdown) {
            $momentum = collect($breakdown)->firstWhere('key', 'momentum');

            return $momentum !== null
                && $momentum['closed'] === 3
                && $momentum['open'] === 1
                && $momentum['episode_count'] === 2 // {BUMI 1-10 Sep} + {BRPT 15 Sep}
                // BUMI episode avg (60000-15000)/2 = +22.500 (menang), BRPT +90000 (menang) -> 2/2.
                && $momentum['episode_win_rate'] === 100.0;
        });
    }
}
