<?php

namespace App\Http\Controllers;

use App\Services\MarketData\IdxMarketSummaryService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * "Market Alerts" -- a descriptive end-of-day monitor (unusual volume, price gap, foreign flow,
 * KSEI ownership shift) across the whole IDX universe. Data comes from the public IDX stock
 * summary; it is NOT real-time, NOT per-transaction, and NOT a trading signal.
 */
class MarketAlertController extends Controller
{
    public function __construct(private readonly IdxMarketSummaryService $summaries) {}

    public function index()
    {
        return view('market-alerts.index', [
            'payload' => $this->summaries->summary(),
        ]);
    }

    public function data(Request $request): JsonResponse
    {
        $fresh = $request->boolean('fresh');

        return response()->json($this->summaries->summary($fresh));
    }
}
