<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Services\MarketData\LiveMarketDataService;
use App\Services\MarketData\MarketDataProviderInterface;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

// Fase DB (+ Fase DC nambah TINS/PTRO/ENRG/RAJA): Signal Radar -- /trades/radar (halaman) +
// /trades/radar-data (polling JSON). SignalRadarService::GABUNGAN/MOMENTUM/BOTTOM_REBOUND_TICKERS
// dipakai penuh di build() (BUMI, DEWA, BRPT, SMGR, ESSA, UNVR, DSSA, TINS, PTRO, ENRG, RAJA -- 11
// ticker unik) -- ticker yg TIDAK sengaja diuji di test tertentu diberi seri historis PENDEK
// (<25 titik) supaya di-skip diam-diam (guard `count($series) < 25`), tanpa perlu craft data
// realistis utk semua 11 ticker di tiap test.
class SignalRadarTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        // Cache historical series di-key per ticker dgn TTL 15 menit -- WAJIB di-flush supaya
        // test lain (atau run sebelumnya) tidak membocorkan seri yg di-fake test lain ke sini.
        //
        // PENTING: Cache::store('file') TIDAK ter-isolasi per environment di codebase ini (path
        // storage/framework/cache/data dipakai bareng testing & dev server) -- data hipotetis yg
        // di-fake di sini (mis. DEWA=[100x9,110]) BISA BOCOR ke halaman /trades/radar yg lagi
        // dibuka manual di browser kalau tidak di-flush lagi setelah test selesai. tearDown()
        // WAJIB ada, jangan dihapus.
        Cache::store('file')->flush();
    }

    protected function tearDown(): void
    {
        Cache::store('file')->flush();
        parent::tearDown();
    }

    /** @return array<string,Stock> */
    private function seedAllTickers(): array
    {
        $stocks = [];
        foreach (['BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'DSSA', 'TINS', 'PTRO', 'ENRG', 'RAJA'] as $code) {
            $stocks[$code] = $this->seedStock($code);
        }

        return $stocks;
    }

    /** Bangun payload JSON ala Yahoo Finance chart API dari daftar closes, tanggal berakhir KEMARIN. */
    private function fakeChartJson(array $closes): array
    {
        $end = now()->timezone('Asia/Jakarta')->subDay()->startOfDay();
        $n = count($closes);
        $timestamps = [];
        for ($i = 0; $i < $n; $i++) {
            $timestamps[] = $end->copy()->subDays($n - 1 - $i)->timestamp;
        }

        return [
            'chart' => [
                'result' => [[
                    'timestamp' => $timestamps,
                    'indicators' => ['quote' => [['close' => $closes]]],
                ]],
            ],
        ];
    }

    /** Bind LiveMarketDataService dgn provider fake yg return harga BERBEDA per kode saham. */
    private function fakeLivePrices(array $priceByCode): void
    {
        // phpunit.xml set STOCK_DATA_SOURCE=snapshot secara default (utk test lain yg baca dari
        // tabel stock_prices) -- LiveMarketDataService::quote() SENGAJA skip provider yg
        // di-inject sama sekali kalau data_source=snapshot (lihat kondisi `$dataSource ===
        // 'snapshot' ? null : $this->provider?->quote($stock)`). WAJIB override ke 'live' di
        // sini, sama seperti pola LiveQuoteApiTest, supaya provider fake di bawah ini benar2
        // dipanggil.
        config(['market.data_source' => 'live']);

        $provider = new class($priceByCode) implements MarketDataProviderInterface
        {
            public function __construct(private array $priceByCode) {}

            public function quote(Stock $stock): ?array
            {
                if (! array_key_exists($stock->code, $this->priceByCode)) {
                    return null;
                }

                $last = $this->priceByCode[$stock->code];

                return [
                    'stock_code' => $stock->code,
                    'open' => $last, 'high' => $last, 'low' => $last, 'close' => $last, 'last' => $last,
                    'volume' => 1000, 'change' => 0, 'change_percent' => 0,
                    'source' => 'fake_radar_test', 'is_live' => true, 'fetched_at' => now(),
                ];
            }
        };

        app()->instance(LiveMarketDataService::class, new LiveMarketDataService($provider, app(PriceSeriesService::class)));
    }

    /** Fake Http utk semua 7 ticker -- default seri pendek (di-skip), override via $overrides. */
    private function fakeHttpForAllTickers(array $overrides = []): void
    {
        $shortSeries = array_fill(0, 5, 100.0); // < 25 -> di-skip guard
        $fakes = [];
        foreach (['BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'DSSA', 'TINS', 'PTRO', 'ENRG', 'RAJA'] as $code) {
            $closes = $overrides[$code] ?? $shortSeries;
            $fakes["query2.finance.yahoo.com/v8/finance/chart/{$code}.JK*"] = Http::response($this->fakeChartJson($closes));
        }
        Http::fake($fakes);
    }

    public function test_guest_cannot_view_radar(): void
    {
        $this->get('/trades/radar')->assertRedirect('/login');
    }

    public function test_radar_page_renders_with_disclaimer(): void
    {
        $user = $this->user();
        $this->seedAllTickers();
        $this->fakeHttpForAllTickers();
        $this->fakeLivePrices(['BUMI' => 100, 'DEWA' => 100, 'BRPT' => 100, 'SMGR' => 100, 'ESSA' => 100, 'UNVR' => 100, 'DSSA' => 100]);

        $this->actingAs($user)->get('/trades/radar')
            ->assertOk()
            ->assertSee('Signal Radar')
            ->assertSee('ESTIMASI LIVE', false);
    }

    public function test_radar_data_gracefully_returns_empty_when_yahoo_unavailable(): void
    {
        $user = $this->user();
        $this->seedAllTickers();
        Http::fake(['query2.finance.yahoo.com/*' => Http::response('', 500)]);
        $this->fakeLivePrices(['BUMI' => 100]);

        $response = $this->actingAs($user)->getJson('/trades/radar-data');

        $response->assertOk();
        $this->assertSame([], $response->json('gabungan'));
        $this->assertSame([], $response->json('momentum'));
        $this->assertSame([], $response->json('bottom_rebound'));
    }

    public function test_gabungan_ret2d_trigger_detected_on_steep_drop(): void
    {
        $user = $this->user();
        $this->seedAllTickers();

        // SMGR: GABUNGAN-only ticker (tidak entangle ke MOMENTUM/BOTTOM_REBOUND) -- 30 hari
        // stabil di 200, lalu closing kemarin turun ke 195. Live price 180 -> ret_2d =
        // (180-195)/195... TUNGGU: ret_2d dihitung combined[-1] vs combined[-3] = live vs
        // closing DUA hari sebelum live (yaitu closing SEBELUM kemarin, bukan kemarin sendiri).
        // Series: [...200 x28, 200(H-2), 195(H-1/kemarin)], live=170.
        // combined = [...,200,195,170] -> ret_2d = (170-200)/200 = -15% (jauh lewat -5%).
        $series = array_fill(0, 28, 200.0);
        $series[] = 200.0; // H-2
        $series[] = 195.0; // H-1 (kemarin)

        $this->fakeHttpForAllTickers(['SMGR' => $series]);
        $this->fakeLivePrices(['SMGR' => 170.0]);

        $response = $this->actingAs($user)->getJson('/trades/radar-data');
        $response->assertOk();

        $smgrRows = collect($response->json('gabungan'))->firstWhere('ticker', 'SMGR');
        $this->assertNotNull($smgrRows, 'SMGR harus muncul di seksi GABUNGAN');
        $this->assertTrue($smgrRows['triggered'], 'SMGR harus triggered=true saat ret_2d jauh melewati -5%');
        $this->assertLessThanOrEqual(0, $smgrRows['ret_2d_distance_pp']);
        $this->assertLessThanOrEqual(-5.0, $smgrRows['ret_2d_pct']);
        // SMGR TIDAK termasuk DRAWDOWN_LEG_TICKERS -- dd_20d_distance_pp harus null.
        $this->assertNull($smgrRows['dd_20d_distance_pp']);
    }

    public function test_momentum_rsi_trigger_detected_on_strong_uptrend(): void
    {
        $user = $this->user();
        $this->seedAllTickers();

        // DSSA: MOMENTUM-only ticker. Uptrend kuat nyaris tanpa penurunan -> RSI mendekati 100,
        // jauh di atas ambang 60.
        $series = [];
        $price = 100.0;
        for ($i = 0; $i < 40; $i++) {
            $price += 3.0; // naik terus, tidak pernah turun -> avgLoss ~0 -> RSI tinggi
            $series[] = $price;
        }

        $this->fakeHttpForAllTickers(['DSSA' => $series]);
        $this->fakeLivePrices(['DSSA' => $price + 5.0]); // lanjut naik

        $response = $this->actingAs($user)->getJson('/trades/radar-data');
        $response->assertOk();

        $dssaRow = collect($response->json('momentum'))->firstWhere('ticker', 'DSSA');
        $this->assertNotNull($dssaRow, 'DSSA harus muncul di seksi MOMENTUM');
        $this->assertTrue($dssaRow['triggered'], 'DSSA harus triggered=true saat RSI jauh di atas 60');
        $this->assertGreaterThan(60, $dssaRow['rsi14_now']);
        $this->assertLessThan(0, $dssaRow['distance_pp']);
    }

    public function test_bottom_rebound_detects_fresh_cross_vs_already_in_zone(): void
    {
        $user = $this->user();
        $this->seedAllTickers();

        // BUMI: 30 hari flat di 100 (bottom_10d kemarin = min 10 hari terakhir = 100 ->
        // threshold = 105), closing kemarin MASIH di bawah threshold (102) -> live price 106 =
        // CROSS BARU hari ini. Butuh total >= 25 titik (guard historicalSeries di service).
        $bumiSeries = array_fill(0, 29, 100.0);
        $bumiSeries[] = 102.0; // H-1 (kemarin), masih < threshold 105

        // DEWA: closing kemarin SUDAH di atas threshold (110 >= 105) -> live tetap tinggi (112)
        // = BUKAN sinyal baru, cuma "sudah di zona".
        $dewaSeries = array_fill(0, 29, 100.0);
        $dewaSeries[] = 110.0; // H-1, SUDAH >= threshold 105

        $this->fakeHttpForAllTickers(['BUMI' => $bumiSeries, 'DEWA' => $dewaSeries]);
        $this->fakeLivePrices(['BUMI' => 106.0, 'DEWA' => 112.0]);

        $response = $this->actingAs($user)->getJson('/trades/radar-data');
        $response->assertOk();

        $bumiRow = collect($response->json('bottom_rebound'))->firstWhere('ticker', 'BUMI');
        $dewaRow = collect($response->json('bottom_rebound'))->firstWhere('ticker', 'DEWA');

        $this->assertNotNull($bumiRow);
        $this->assertTrue($bumiRow['triggered_today'], 'BUMI harus cross baru hari ini');
        $this->assertFalse($bumiRow['already_in_zone']);

        $this->assertNotNull($dewaRow);
        $this->assertFalse($dewaRow['triggered_today'], 'DEWA TIDAK boleh dianggap sinyal baru -- sudah di zona sejak kemarin');
        $this->assertTrue($dewaRow['already_in_zone']);
    }
}
