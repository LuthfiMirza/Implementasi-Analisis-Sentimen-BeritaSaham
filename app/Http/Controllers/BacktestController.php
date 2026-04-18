<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\Analytics\BacktestService;
use Illuminate\Http\Request;

class BacktestController extends Controller
{
    public function index(Request $request)
    {
        $code = $request->get('code', 'BBCA');
        $forward = (int) $request->get('forward', 5);
        $step = (int) $request->get('step', 3);
        $threshold = (float) $request->get('threshold', 1.0);
        $includeMacroNews = $request->boolean('include_macro_news', true);
        $macroRegulatorySignal = $request->query->has('macro_regulatory_signal')
            ? $request->boolean('macro_regulatory_signal')
            : null;

        $stock = Stock::where('code', strtoupper($code))
            ->where('is_active', true)
            ->firstOrFail();
        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        $service = app(BacktestService::class);
        $result = $service->runForStock(
            $stock,
            30,
            $forward,
            $step,
            $threshold,
            $includeMacroNews,
            $macroRegulatorySignal
        );

        return view('backtest.index', compact(
            'result',
            'stock',
            'stocks',
            'code',
            'forward',
            'step',
            'threshold',
            'includeMacroNews',
            'macroRegulatorySignal'
        ));
    }

    public function all(Request $request)
    {
        $forward = (int) $request->get('forward', 5);
        $threshold = (float) $request->get('threshold', 1.0);
        $includeMacroNews = $request->boolean('include_macro_news', true);
        $macroRegulatorySignal = $request->query->has('macro_regulatory_signal')
            ? $request->boolean('macro_regulatory_signal')
            : null;

        $service = app(BacktestService::class);
        $data = $service->runAll(30, $forward, 3, $threshold, $includeMacroNews, $macroRegulatorySignal);

        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        return view('backtest.all', array_merge(
            $data,
            compact('stocks', 'forward', 'threshold', 'includeMacroNews', 'macroRegulatorySignal')
        ));
    }
}
