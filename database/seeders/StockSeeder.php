<?php

namespace Database\Seeders;

use App\Models\Stock;
use App\Models\StockAlias;
use App\Models\StockPrice;
use App\Models\User;
use App\Models\UserWatchlist;
use Carbon\Carbon;
use Illuminate\Database\Seeder;

class StockSeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
        $stocks = [
            ['code' => 'BBCA', 'company_name' => 'Bank Central Asia Tbk', 'sector' => 'Perbankan', 'base_price' => 9200, 'aliases' => ['BCA']],
            ['code' => 'BBRI', 'company_name' => 'Bank Rakyat Indonesia Tbk', 'sector' => 'Perbankan', 'base_price' => 5500, 'aliases' => ['BRI']],
            ['code' => 'BMRI', 'company_name' => 'Bank Mandiri Tbk', 'sector' => 'Perbankan', 'base_price' => 6000, 'aliases' => ['Mandiri']],
            ['code' => 'TLKM', 'company_name' => 'Telkom Indonesia Tbk', 'sector' => 'Telekomunikasi', 'base_price' => 3800, 'aliases' => ['Telkom']],
            ['code' => 'ASII', 'company_name' => 'Astra International Tbk', 'sector' => 'Otomotif', 'base_price' => 5800, 'aliases' => ['Astra']],
            ['code' => 'GOTO', 'company_name' => 'GoTo Gojek Tokopedia Tbk', 'sector' => 'Teknologi', 'base_price' => 90, 'aliases' => ['GoTo', 'Gojek']],
            ['code' => 'INDF', 'company_name' => 'Indofood Sukses Makmur Tbk', 'sector' => 'Konsumsi', 'base_price' => 6500, 'aliases' => ['Indofood']],
            ['code' => 'ICBP', 'company_name' => 'Indofood CBP Sukses Makmur Tbk', 'sector' => 'Konsumsi', 'base_price' => 9700, 'aliases' => ['ICBP']],
            ['code' => 'ADRO', 'company_name' => 'Adaro Energy Indonesia Tbk', 'sector' => 'Energi', 'base_price' => 3100, 'aliases' => ['Adaro']],
            ['code' => 'BUMI', 'company_name' => 'Bumi Resources Tbk', 'sector' => 'Pertambangan', 'base_price' => 135, 'aliases' => ['Bumi Resources']],
            ['code' => 'DEWA', 'company_name' => 'Darma Henwa Tbk', 'sector' => 'Pertambangan', 'base_price' => 72, 'aliases' => ['Darma Henwa']],
            ['code' => 'UNVR', 'company_name' => 'Unilever Indonesia Tbk', 'sector' => 'Konsumsi', 'base_price' => 4700, 'aliases' => ['Unilever']],
        ];

        foreach ($stocks as $data) {
            $stock = Stock::updateOrCreate(
                ['code' => $data['code']],
                [
                    'company_name' => $data['company_name'],
                    'sector' => $data['sector'] ?? null,
                    'description' => $data['company_name'].' tercatat di Bursa Efek Indonesia.',
                    'exchange' => 'IDX',
                    'tradingview_symbol' => 'IDX:'.$data['code'],
                    'yahoo_symbol' => $data['code'].'.JK',
                    'is_active' => true,
                ]
            );

            foreach ($data['aliases'] as $alias) {
                StockAlias::updateOrCreate(
                    ['stock_id' => $stock->id, 'alias_name' => $alias],
                    []
                );
            }

            $this->seedPrices($stock, $data['base_price']);
        }

        $demoUser = User::where('email', 'user@sentimena.test')->first();
        if ($demoUser) {
            $watchlistCodes = ['BBCA', 'BBRI', 'TLKM', 'GOTO', 'ASII'];
            foreach ($watchlistCodes as $code) {
                $stock = Stock::where('code', $code)->first();
                if ($stock) {
                    UserWatchlist::firstOrCreate([
                        'user_id' => $demoUser->id,
                        'stock_id' => $stock->id,
                    ]);
                }
            }
        }
    }

    protected function seedPrices(Stock $stock, float $basePrice): void
    {
        $startDate = Carbon::now()->subDays(30);

        for ($i = 0; $i < 30; $i++) {
            $date = $startDate->copy()->addDays($i)->setTime(15, 0);
            $drift = (sin($i / 5) * 0.02 * $basePrice);
            $close = max(10, $basePrice + $drift + random_int(-30, 30));
            $open = $close + random_int(-15, 15);
            $high = max($open, $close) + random_int(0, 20);
            $low = max(1, min($open, $close) - random_int(0, 20));

            StockPrice::updateOrCreate(
                [
                    'stock_id' => $stock->id,
                    'price_date' => $date,
                    'interval_type' => '1d',
                ],
                [
                    'open' => $open,
                    'high' => $high,
                    'low' => $low,
                    'close' => $close,
                    'volume' => random_int(100_000, 10_000_000),
                    'source' => 'seed',
                ]
            );
        }
    }
}
