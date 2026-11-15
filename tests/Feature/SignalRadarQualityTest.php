<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Models\User;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\MarketData\MarketDataProviderInterface;
use App\Services\Stocks\PriceSeriesService;
use App\Services\Trading\SignalRadarService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class SignalRadarQualityTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Cache::store('file')->flush();
    }

    protected function tearDown(): void
    {
        Cache::store('file')->flush();
        parent::tearDown();
    }

    public function test_radar_data_includes_quality_grader_fields_on_candidates(): void
    {
        $user = User::factory()->create();

        // Seed stock SMGR
        Stock::create([
            'code' => 'SMGR',
            'company_name' => 'Semen Indonesia',
            'is_active' => true,
        ]);

        config(['market.data_source' => 'live']);

        $provider = new class implements MarketDataProviderInterface {
            public function quote(Stock $stock): ?array
            {
                if ($stock->code !== 'SMGR') {
                    return null;
                }
                return [
                    'stock_code' => 'SMGR',
                    'open' => 3900.0,
                    'high' => 3950.0,
                    'low' => 3750.0,
                    'close' => 3800.0,
                    'last' => 3800.0,
                    'volume' => 5000000,
                    'change' => -100,
                    'change_percent' => -2.5,
                    'source' => 'fake_radar_test',
                    'is_live' => true,
                    'fetched_at' => now(),
                ];
            }
        };

        app()->instance(LiveMarketDataService::class, new LiveMarketDataService($provider, app(PriceSeriesService::class)));

        // 30 days of closes ending yesterday
        $end = now()->timezone('Asia/Jakarta')->subDay()->startOfDay();
        $closes = array_merge(array_fill(0, 28, 4200.0), [4000.0, 3900.0]);
        $timestamps = [];
        $n = count($closes);
        for ($i = 0; $i < $n; $i++) {
            $timestamps[] = $end->copy()->subDays($n - 1 - $i)->timestamp;
        }

        Http::fake([
            'https://query2.finance.yahoo.com/v8/finance/chart/SMGR.JK*' => Http::response([
                'chart' => [
                    'result' => [
                        [
                            'timestamp' => $timestamps,
                            'indicators' => [
                                'quote' => [
                                    ['close' => $closes],
                                ],
                            ],
                        ],
                    ],
                ],
            ], 200),
            'https://query2.finance.yahoo.com/*' => Http::response([
                'chart' => [
                    'result' => [
                        [
                            'timestamp' => [now()->subDays(2)->timestamp],
                            'indicators' => [
                                'quote' => [
                                    ['close' => [100.0]],
                                ],
                            ],
                        ],
                    ],
                ],
            ], 200),
        ]);

        $radarService = app(SignalRadarService::class);
        $data = $radarService->build();

        $this->assertArrayHasKey('gabungan', $data);
        $smgr = collect($data['gabungan'])->firstWhere('ticker', 'SMGR');
        $this->assertNotNull($smgr, 'SMGR harus muncul di seksi GABUNGAN');
        $this->assertArrayHasKey('quality', $smgr);
        $this->assertArrayHasKey('grade', $smgr['quality']);
        $this->assertArrayHasKey('score', $smgr['quality']);
        $this->assertArrayHasKey('status', $smgr['quality']);
        $this->assertArrayHasKey('recommended_sizing_pct', $smgr['quality']);
        $this->assertArrayHasKey('action_advice', $smgr['quality']);
        $this->assertContains($smgr['quality']['grade'], ['A+', 'A', 'B', 'C']);
        $this->assertGreaterThanOrEqual(10, $smgr['quality']['score']);
    }
}
