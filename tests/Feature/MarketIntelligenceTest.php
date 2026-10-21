<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class MarketIntelligenceTest extends TestCase
{
    public function test_guest_is_redirected_to_login()
    {
        $response = $this->get('/market-intelligence');
        $response->assertRedirect('/login');
    }

    public function test_authenticated_user_can_view_market_intelligence_index()
    {
        $user = User::factory()->make(['id' => 1]);

        $response = $this->actingAs($user)->get('/market-intelligence');

        $response->assertStatus(200);
        $response->assertSee('Market Intelligence', false);
        $response->assertSee('REBOUND TERKONFIRMASI', false);
        $response->assertSee('market_regime_research_20261021', false);
    }

    public function test_authenticated_user_can_view_specific_research_report()
    {
        $user = User::factory()->make(['id' => 1]);

        $response = $this->actingAs($user)->get('/market-intelligence/rebound_prediction_scenarios_20261020');

        $response->assertStatus(200);
        $response->assertSee('Proyeksi Tanggal & Skenario Rebound IHSG');
        $response->assertSee('Checklist 3 Syarat Rebound');
    }

    public function test_non_existent_report_returns_404()
    {
        $user = User::factory()->make(['id' => 1]);

        $response = $this->actingAs($user)->get('/market-intelligence/non_existent_slug_12345');

        $response->assertStatus(404);
    }
}
