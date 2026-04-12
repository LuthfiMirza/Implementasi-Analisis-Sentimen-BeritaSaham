<?php

namespace Database\Seeders;

use App\Models\FetchLog;
use App\Models\SystemSetting;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        $this->call([
            UserSeeder::class,
            StockSeeder::class,
            NewsSeeder::class,
            FundamentalStockSeeder::class,
        ]);

        FetchLog::factory(5)->create();

        SystemSetting::updateOrCreate(
            ['key' => 'news_provider'],
            ['value' => ['value' => env('NEWS_PROVIDER', 'mock')]]
        );
        SystemSetting::updateOrCreate(
            ['key' => 'stock_chart_mode'],
            ['value' => ['value' => env('STOCK_CHART_MODE', 'tradingview')]]
        );
    }
}
