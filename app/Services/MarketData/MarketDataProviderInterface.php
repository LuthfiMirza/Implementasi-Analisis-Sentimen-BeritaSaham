<?php

namespace App\Services\MarketData;

use App\Models\Stock;

interface MarketDataProviderInterface
{
    public function quote(Stock $stock): ?array;
}
