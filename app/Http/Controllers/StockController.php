<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\Stocks\StockDashboardService;
use Illuminate\Http\Request;

class StockController extends Controller
{
    public function __construct(protected StockDashboardService $dashboardService)
    {
    }

    public function show(string $code, Request $request)
    {
        $interval = $request->query('interval', '1d');
        $data = $this->dashboardService->getDashboardData($code, $request->user(), $interval);
        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        return view('dashboard.index', [
            ...$data,
            'stocks' => $stocks,
            'interval' => $interval,
        ]);
    }

    public function search(Request $request)
    {
        $term = $request->query('q', '');

        $results = Stock::query()
            ->where(function ($query) use ($term) {
                $query->where('code', 'like', '%'.$term.'%')
                    ->orWhere('company_name', 'like', '%'.$term.'%');
            })
            ->limit(10)
            ->get(['id', 'code', 'company_name', 'sector', 'tradingview_symbol']);

        return response()->json($results);
    }
}
