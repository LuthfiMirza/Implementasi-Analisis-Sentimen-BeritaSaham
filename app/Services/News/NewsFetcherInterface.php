<?php

namespace App\Services\News;

use App\Models\Stock;

interface NewsFetcherInterface
{
    /**
     * @return array<int, array<string, mixed>>
     */
    public function fetchForStock(Stock $stock, int $limit = 10): array;
}
