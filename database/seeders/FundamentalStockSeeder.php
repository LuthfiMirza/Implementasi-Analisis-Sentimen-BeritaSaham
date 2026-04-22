<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Stock;

class FundamentalStockSeeder extends Seeder
{
    public function run(): void
    {
        $data = [
            'BBCA' => [
                'pbv' => 3.8, 'per' => 18.5, 'roe' => 21.2,
                'der' => 5.2, 'eps' => 362, 'dividend_yield' => 2.8,
            ],
            'BBRI' => [
                'pbv' => 2.1, 'per' => 10.2, 'roe' => 18.5,
                'der' => 6.8, 'eps' => 415, 'dividend_yield' => 5.2,
            ],
            'BMRI' => [
                'pbv' => 2.3, 'per' => 11.5, 'roe' => 19.8,
                'der' => 7.1, 'eps' => 520, 'dividend_yield' => 4.8,
            ],
            'TLKM' => [
                'pbv' => 1.8, 'per' => 14.2, 'roe' => 12.5,
                'der' => 0.8, 'eps' => 225, 'dividend_yield' => 6.1,
            ],
            'ASII' => [
                'pbv' => 1.2, 'per' => 8.5, 'roe' => 14.2,
                'der' => 1.0, 'eps' => 612, 'dividend_yield' => 4.5,
            ],
            'GOTO' => [
                'pbv' => 1.1, 'per' => null, 'roe' => -8.5,
                'der' => 0.3, 'eps' => -12, 'dividend_yield' => 0,
            ],
            'INDF' => [
                'pbv' => 1.0, 'per' => 7.8, 'roe' => 13.1,
                'der' => 0.9, 'eps' => 845, 'dividend_yield' => 5.8,
            ],
            'ICBP' => [
                'pbv' => 3.2, 'per' => 15.6, 'roe' => 20.5,
                'der' => 0.7, 'eps' => 712, 'dividend_yield' => 3.2,
            ],
            'ADRO' => [
                'pbv' => 1.5, 'per' => 5.2, 'roe' => 28.5,
                'der' => 0.4, 'eps' => 1250, 'dividend_yield' => 12.5,
            ],
            'BUMI' => [
                'pbv' => 0.9, 'per' => 6.8, 'roe' => 9.4,
                'der' => 3.2, 'eps' => 18, 'dividend_yield' => 0.0,
            ],
            'DEWA' => [
                'pbv' => 0.7, 'per' => 6.4, 'roe' => 11.5,
                'der' => 1.8, 'eps' => 9, 'dividend_yield' => 0.0,
            ],
            'UNVR' => [
                'pbv' => 18.5, 'per' => 22.1, 'roe' => 85.2,
                'der' => 2.1, 'eps' => 108, 'dividend_yield' => 4.1,
            ],
        ];

        foreach ($data as $code => $values) {
            Stock::where('code', $code)->update(array_merge($values, [
                'fundamentals_updated_at' => '2025-12-31',
            ]));
        }
    }
}
