<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class HealthCheckTest extends TestCase
{
    use RefreshDatabase;

    public function test_health_endpoint_returns_json_structure_with_services_status(): void
    {
        Http::fake([
            'http://127.0.0.1:8002/docs' => Http::response('<html>docs</html>', 200),
            'http://127.0.0.1:8001/docs' => Http::response('<html>docs</html>', 200),
        ]);

        $response = $this->get('/health');

        $response->assertStatus(200);
        $response->assertJsonStructure([
            'status',
            'timestamp',
            'services' => [
                'database' => ['status', 'open_trades', 'closed_trades'],
                'sentiment_api' => ['status', 'port'],
                'prediction_api' => ['status', 'port'],
                'scheduler' => ['status'],
            ],
            'summary',
        ]);

        $json = $response->json();
        $this->assertSame('ok', $json['services']['database']['status']);
        $this->assertSame('ok', $json['services']['sentiment_api']['status']);
        $this->assertSame('ok', $json['services']['prediction_api']['status']);
    }
}

