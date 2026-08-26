<?php

namespace Tests\Feature;

use App\Models\SystemSetting;
use App\Models\Trade;
use Tests\TestCase;

// Fase DE: Total Exposure Warning -- deteksi konsentrasi modal (total & per-sektor/per-ticker)
// di posisi terbuka. Kartu ringkasan di /trades (server-side) + kalkulator hipotetis di modal
// Catat Trade Baru (client-side JS, tidak dites langsung di sini -- PHPUnit tidak eksekusi JS,
// tapi kontrak angka & ambang di-cross-check manual sbg dokumentasi).
class TotalExposureWarningTest extends TestCase
{
    public function test_exposure_card_hidden_when_no_open_positions(): void
    {
        $user = $this->user();

        // "🎯 Total Exposure" (label kartu, hanya render di dalam @if($open->count()>0)) --
        // BUKAN cuma "Total Exposure" polos, krn frasa itu jg muncul di komentar JS statis
        // (selalu ada di HTML output apapun kondisinya, beda dari kartu yg beneran conditional).
        $this->actingAs($user)->get('/trades')
            ->assertOk()
            ->assertDontSee('🎯 Total Exposure')
            ->assertDontSee('OVER-EXPOSED')
            ->assertDontSee('WASPADA');
    }

    public function test_exposure_status_is_danger_when_over_100_percent_of_capital(): void
    {
        $user = $this->user();
        SystemSetting::updateOrCreate(['key' => 'position_sizing_capital'], ['value' => ['value' => 30_000_000]]);
        SystemSetting::updateOrCreate(['key' => 'position_sizing_risk_pct'], ['value' => ['value' => 1]]);

        $dssa = $this->seedStock('DSSA', ['sector' => 'Energy']);
        $brpt = $this->seedStock('BRPT', ['sector' => 'Basic Materials']);

        // Replikasi kondisi nyata yg memicu fitur ini: 3 posisi DSSA + 1 BRPT, total exposure
        // Rp39.675.500 vs modal Rp30jt = 132,3% (danger), DSSA 75,2% dari exposure (danger).
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $dssa->id, 'ticker' => 'DSSA', 'status' => 'open', 'entry_price' => 1020, 'lot_size' => 9800, 'position_value' => 9_996_000, 'entry_date' => now()]);
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $dssa->id, 'ticker' => 'DSSA', 'status' => 'open', 'entry_price' => 1055, 'lot_size' => 9400, 'position_value' => 9_917_000, 'entry_date' => now()]);
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $dssa->id, 'ticker' => 'DSSA', 'status' => 'open', 'entry_price' => 1065, 'lot_size' => 9300, 'position_value' => 9_904_500, 'entry_date' => now()]);
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $brpt->id, 'ticker' => 'BRPT', 'status' => 'open', 'entry_price' => 1860, 'lot_size' => 5300, 'position_value' => 9_858_000, 'entry_date' => now()]);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk();
        $response->assertSee('OVER-EXPOSED');
        $response->assertSee('132.3%', false);
        $response->assertSee('Energy', false);
        $response->assertSee('75.2%', false);
    }

    public function test_exposure_status_is_safe_when_well_diversified(): void
    {
        $user = $this->user();
        SystemSetting::updateOrCreate(['key' => 'position_sizing_capital'], ['value' => ['value' => 100_000_000]]);
        SystemSetting::updateOrCreate(['key' => 'position_sizing_risk_pct'], ['value' => ['value' => 1]]);

        $bbca = $this->seedStock('BBCA', ['sector' => 'Keuangan']);
        Trade::factory()->create(['user_id' => $user->id, 'stock_id' => $bbca->id, 'ticker' => 'BBCA', 'status' => 'open', 'entry_price' => 10000, 'lot_size' => 500, 'position_value' => 5_000_000, 'entry_date' => now()]);

        $response = $this->actingAs($user)->get('/trades');

        $response->assertOk();
        $response->assertDontSee('OVER-EXPOSED');
        $response->assertDontSee('WASPADA');
    }

    public function test_sector_concentration_formula_matches_manual_calculation(): void
    {
        // Dokumentasi kontrak angka -- WAJIB match dgn logic JS updateExposureWarning() di
        // index.blade.php kalau formula ini diubah di kedua tempat.
        $totalValue = 39_675_500;
        $dssaValue = 9_996_000 + 9_917_000 + 9_904_500; // 29.817.500
        $sectorPct = round($dssaValue / $totalValue * 100, 1);

        $this->assertSame(29_817_500.0, (float) $dssaValue);
        $this->assertSame(75.2, $sectorPct);

        $capital = 30_000_000;
        $totalPct = round($totalValue / $capital * 100, 1);
        $this->assertSame(132.3, $totalPct);
    }
}
