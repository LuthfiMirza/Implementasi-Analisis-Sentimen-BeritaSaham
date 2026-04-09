<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\Stocks\StockDashboardService;
use Illuminate\Http\Request;

class DashboardController extends Controller
{
    public function __construct(protected StockDashboardService $dashboardService)
    {
    }

    public function index(Request $request)
    {
        $code = $request->query('code', config('dashboard.default_stock', 'BBCA'));
        $interval = $request->query('interval', '1d');
        $data = $this->dashboardService->getDashboardData($code, $request->user(), $interval);
        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        return view('dashboard.index', [
            ...$data,
            'stocks' => $stocks,
            'interval' => $interval,
        ]);
    }
}
