<?php

namespace App\Services\MarketData;

use App\Models\Stock;

class DemoMarketDataProvider implements MarketDataProviderInterface
{
    public function quote(Stock $stock): ?array
    {
        // Demo provider: generates pseudo-live data around a base value
        $base = 5000 + (mt_rand(-100, 100));
        $open = $base - mt_rand(-30, 30);
        $high = $base + mt_rand(0, 60);
        $low = $base - mt_rand(0, 60);
        $close = $base + mt_rand(-20, 20);
        $volume = mt_rand(100000, 5000000);

        return [
            'stock_code' => $stock->code,
            'open' => $open,
            'high' => $high,
            'low' => $low,
            'close' => $close,
            'last' => $close,
            'volume' => $volume,
            'change' => $close - $open,
            'change_percent' => $open != 0 ? (($close - $open) / $open) * 100 : 0,
            'source' => 'demo',
            'is_live' => true,
            'fetched_at' => now(),
        ];
    }
}
