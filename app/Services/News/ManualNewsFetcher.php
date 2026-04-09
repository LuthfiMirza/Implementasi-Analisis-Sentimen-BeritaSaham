<?php

namespace App\Services\News;

use App\Models\Stock;

class ManualNewsFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        // Manual mode expects data to be inserted via admin/import UI
        return [];
    }
}
