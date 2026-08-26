<?php

namespace Tests\Feature;

use App\Models\SystemSetting;
use Tests\TestCase;

// Fase DD: Position Sizing Calculator -- modal trading + risk% (system_settings) dipakai
// kalkulator "lot disarankan" di modal Catat Trade Baru (/trades). Formula: risk_amount =
// capital * risk_pct/100; suggested_shares = floor(risk_amount / (entry-sl) / 100) * 100
// (dibulatkan KE BAWAH ke kelipatan 100 lembar -- 1 lot IDX -- supaya risk aktual tidak pernah
// melebihi target). Kalkulator sendiri jalan client-side (JS di index.blade.php) -- test di sini
// fokus ke server-side: settings tersimpan benar & halaman render angka yg konsisten dgn formula.
class PositionSizingTest extends TestCase
{
    public function test_guest_cannot_update_position_sizing(): void
    {
        $this->post('/trades/position-sizing', ['capital' => 30_000_000, 'risk_pct' => 1])
            ->assertRedirect('/login');
    }

    public function test_user_can_save_capital_and_risk_percent(): void
    {
        $user = $this->user();

        $response = $this->actingAs($user)->post('/trades/position-sizing', [
            'capital' => 30_000_000,
            'risk_pct' => 1.5,
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('status');

        $capital = SystemSetting::where('key', 'position_sizing_capital')->first();
        $risk = SystemSetting::where('key', 'position_sizing_risk_pct')->first();

        $this->assertNotNull($capital);
        $this->assertNotNull($risk);
        $this->assertSame(30_000_000.0, (float) $capital->value['value']);
        $this->assertSame(1.5, (float) $risk->value['value']);
    }

    public function test_saved_settings_persist_and_can_be_updated(): void
    {
        $user = $this->user();

        $this->actingAs($user)->post('/trades/position-sizing', ['capital' => 10_000_000, 'risk_pct' => 1]);
        $this->actingAs($user)->post('/trades/position-sizing', ['capital' => 50_000_000, 'risk_pct' => 2]);

        // updateOrCreate -- harus 1 baris per key, bukan bertumpuk tiap kali disimpan ulang.
        $this->assertDatabaseCount('system_settings', 2);

        $capital = SystemSetting::where('key', 'position_sizing_capital')->first();
        $this->assertSame(50_000_000.0, (float) $capital->value['value']);
    }

    public function test_invalid_input_is_rejected(): void
    {
        $user = $this->user();

        $response = $this->actingAs($user)->post('/trades/position-sizing', [
            'capital' => -5000, // negatif tidak masuk akal
            'risk_pct' => 0,     // di bawah minimum 0.1
        ]);

        $response->assertSessionHasErrors(['capital', 'risk_pct']);
        $this->assertDatabaseCount('system_settings', 0);
    }

    public function test_trades_page_shows_prompt_when_sizing_not_configured(): void
    {
        $user = $this->user();

        $this->actingAs($user)->get('/trades')
            ->assertOk()
            ->assertSee('Belum diatur');
    }

    public function test_trades_page_shows_saved_capital_and_max_loss(): void
    {
        $user = $this->user();
        SystemSetting::updateOrCreate(['key' => 'position_sizing_capital'], ['value' => ['value' => 20_000_000]]);
        SystemSetting::updateOrCreate(['key' => 'position_sizing_risk_pct'], ['value' => ['value' => 1]]);

        // 20jt x 1% = 200rb maks rugi/trade -- angka ini harus muncul di halaman (bukti kalkulasi
        // server-side benar, dipakai jg sbg basis kalkulator JS client-side).
        $this->actingAs($user)->get('/trades')
            ->assertOk()
            ->assertSee('Rp20.000.000', false)
            ->assertSee('1%', false)
            ->assertSee('Rp200.000', false);
    }

    public function test_suggested_lot_calculation_rounds_down_to_nearest_100_shares(): void
    {
        // Verifikasi manual formula yg dipakai JS (updateSuggestedLot() di index.blade.php) --
        // dicek di sini sbg dokumentasi kontrak angka, bukan eksekusi JS beneran (JS tidak
        // dieksekusi di PHPUnit). Kalkulator client-side WAJIB match perhitungan ini.
        $capital = 30_000_000;
        $riskPct = 1.0;
        $entry = 1000;
        $stopLoss = 980;

        $riskAmount = $capital * $riskPct / 100; // Rp300.000
        $slDistance = $entry - $stopLoss; // Rp20/lembar
        $suggestedShares = floor($riskAmount / $slDistance / 100) * 100; // floor(15000/100)*100

        $this->assertSame(300_000.0, $riskAmount);
        $this->assertSame(15_000.0, $suggestedShares); // 150 lot, TIDAK ada sisa desimal ganjil
        $this->assertSame(0.0, fmod($suggestedShares, 100)); // selalu kelipatan 100 lembar (1 lot)
    }
}
