<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class StockQuoteApiTest extends TestCase
{
    public function test_stock_quote_api_returns_required_json_keys(): void
    {
        Config::set('market.data_source', 'snapshot');
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 3);

        $response = $this->getJson('/api/stocks/BBCA/quote');

        // Frontend quote cards require all market fields to render safely.
        $response->assertOk()->assertJsonStructure([
            'last', 'open', 'high', 'low', 'volume', 'change', 'change_percent', 'source', 'is_live', 'fetched_at',
        ]);
    }

    public function test_quote_falls_back_to_stock_prices_when_live_provider_is_down(): void
    {
        Config::set('market.data_source', 'live');
        Config::set('market.provider', 'http');
        Config::set('market.base_url', 'https://market.test/chart');
        Config::set('market.fallback_to_snapshot', true);
        Http::fake(['market.test/*' => Http::response(null, 503)]);
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 3);

        $response = $this->getJson('/api/stocks/BBCA/quote');

        // Snapshot fallback keeps dashboards usable when live market data is unavailable.
        $response->assertOk()
            ->assertJsonPath('source', 'backend_snapshot')
            ->assertJsonPath('is_live', false);
    }
}
