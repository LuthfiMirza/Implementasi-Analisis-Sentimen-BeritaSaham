<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Models\Trade;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TradeLaporanMfeTest extends TestCase
{
    use RefreshDatabase;

    public function test_laporan_page_renders_mfe_excursion_analytics_and_trailing_tuning(): void
    {
        $user = User::factory()->create();

        $stock = Stock::create([
            'code' => 'DEWA',
            'company_name' => 'Dharma Henwa Tbk',
            'is_active' => true,
        ]);

        Trade::create([
            'user_id' => $user->id,
            'stock_id' => $stock->id,
            'ticker' => 'DEWA',
            'direction' => 'long',
            'strategy_label' => 'gabungan',
            'entry_date' => now()->subDays(10),
            'exit_date' => now()->subDays(5),
            'entry_price' => 100.0,
            'stop_loss' => 96.5,
            'target_1' => 105.0,
            'lot_size' => 1000,
            'quantity' => 1000,
            'position_value' => 10000000.0,
            'exit_price' => 108.0,
            'pnl_percent' => 8.0,
            'pnl_total' => 800000.0,
            'status' => 'closed',
            'result' => 'hit_trailing_stop',
            'signal_quality' => 'A+',
            'indicators_snapshot' => [
                'rsi_14' => 36.5,
                'lower_wick_pct' => 1.8,
                'vol_ratio_ma20' => 1.6,
                'exit_mfe_pct' => 10.2,
                'peak_price' => 110.2,
                'grade' => 'A+',
            ],
        ]);

        $response = $this->actingAs($user)->get('/trades/laporan');

        $response->assertOk();
        $response->assertSee('Analisis Ekskursi MFE', false);
        $response->assertSee('Optimalisasi Trailing Stop', false);
        $response->assertSee('Efisiensi Kunci Cuan', false);
        $response->assertSee('Simulasi Trailing (1.5%–3.0%)', false);
        $response->assertSee('Rekomendasi per Tier', false);
    }
}
