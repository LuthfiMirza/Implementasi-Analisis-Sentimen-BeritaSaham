<?php

namespace Tests\Feature;

use App\Models\Stock;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class BackfillHistoricalNewsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_dry_run_estimates_requests_without_http_calls(): void
    {
        Stock::factory()->create(['code' => 'BBCA', 'is_active' => true]);
        Http::preventStrayRequests();

        $this->artisan('news:backfill-historical', [
            '--from' => '2025-10-01',
            '--to' => '2025-11-15',
            '--ticker' => ['BBCA'],
            '--source' => ['gdelt', 'newsapi'],
            '--dry-run' => true,
        ])->expectsOutputToContain('Historical news backfill DRY-RUN')
            ->expectsOutputToContain('Subtotal gdelt: 2 request')
            ->expectsOutputToContain('Subtotal newsapi: 2 request')
            ->expectsOutputToContain('Estimated total requests: 4')
            ->assertSuccessful();

        Http::assertNothingSent();
    }
}
