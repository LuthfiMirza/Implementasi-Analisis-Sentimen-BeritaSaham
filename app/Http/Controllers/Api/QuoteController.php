<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Stock;
use App\Services\MarketData\LiveMarketDataService;
use Illuminate\Http\JsonResponse;

class QuoteController extends Controller
{
    public function show(string $code, LiveMarketDataService $service): JsonResponse
    {
        $stock = Stock::where('code', strtoupper($code))->firstOrFail();
        $quote = $service->quote($stock);

        if (! $quote) {
            return response()->json(['message' => 'Quote tidak tersedia'], 404);
        }

        return response()->json($quote);
    }
}
