<?php

namespace App\Http\Controllers;

use App\Models\Stock;
use App\Services\Analytics\BacktestService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;

class BacktestController extends Controller
{
    protected const CACHE_TTL_MINUTES = 15;

    public function index(Request $request)
    {
        $code = $request->get('code', 'BBCA');
        $forward = (int) $request->get('forward', 5);
        $step = (int) $request->get('step', 3);
        $threshold = (float) $request->get('threshold', 1.0);
        $maxWindows = max(5, (int) $request->get('max_windows', 10));
        $includeMacroNews = $request->boolean('include_macro_news', true);
        $macroRegulatorySignal = $request->query->has('macro_regulatory_signal')
            ? $request->boolean('macro_regulatory_signal')
            : null;

        $stock = Stock::where('code', strtoupper($code))
            ->where('is_active', true)
            ->firstOrFail();
        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        $service = app(BacktestService::class);
        $result = Cache::store('file')->remember(
            $this->stockCacheKey(
                $stock->code,
                $forward,
                $step,
                $threshold,
                $includeMacroNews,
                $macroRegulatorySignal,
                $maxWindows
            ),
            now()->addMinutes(self::CACHE_TTL_MINUTES),
            fn () => $service->runForStock(
                $stock,
                30,
                $forward,
                $step,
                $threshold,
                $includeMacroNews,
                $macroRegulatorySignal,
                $maxWindows
            )
        );

        return view('backtest.index', compact(
            'result',
            'stock',
            'stocks',
            'code',
            'forward',
            'step',
            'threshold',
            'maxWindows',
            'includeMacroNews',
            'macroRegulatorySignal'
        ));
    }

    public function all(Request $request)
    {
        $forward = (int) $request->get('forward', 5);
        $threshold = (float) $request->get('threshold', 1.0);
        $maxWindows = max(5, (int) $request->get('max_windows', 5));
        $includeMacroNews = $request->boolean('include_macro_news', true);
        $macroRegulatorySignal = $request->query->has('macro_regulatory_signal')
            ? $request->boolean('macro_regulatory_signal')
            : null;

        $service = app(BacktestService::class);
        $data = Cache::store('file')->remember(
            $this->allStocksCacheKey(
                $forward,
                $threshold,
                $includeMacroNews,
                $macroRegulatorySignal,
                $maxWindows
            ),
            now()->addMinutes(self::CACHE_TTL_MINUTES),
            fn () => $service->runAll(30, $forward, 3, $threshold, $includeMacroNews, $macroRegulatorySignal, $maxWindows)
        );

        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        return view('backtest.all', array_merge(
            $data,
            compact('stocks', 'forward', 'threshold', 'maxWindows', 'includeMacroNews', 'macroRegulatorySignal')
        ));
    }

    protected function stockCacheKey(
        string $code,
        int $forward,
        int $step,
        float $threshold,
        bool $includeMacroNews,
        ?bool $macroRegulatorySignal,
        int $maxWindows
    ): string {
        return implode(':', [
            'backtest',
            'stock',
            strtoupper($code),
            'f'.$forward,
            's'.$step,
            't'.number_format($threshold, 2, '.', ''),
            'macro_news_'.(int) $includeMacroNews,
            'macro_signal_'.($macroRegulatorySignal === null ? 'auto' : (int) $macroRegulatorySignal),
            'w'.$maxWindows,
        ]);
    }

    protected function allStocksCacheKey(
        int $forward,
        float $threshold,
        bool $includeMacroNews,
        ?bool $macroRegulatorySignal,
        int $maxWindows
    ): string {
        return implode(':', [
            'backtest',
            'all',
            'f'.$forward,
            't'.number_format($threshold, 2, '.', ''),
            'macro_news_'.(int) $includeMacroNews,
            'macro_signal_'.($macroRegulatorySignal === null ? 'auto' : (int) $macroRegulatorySignal),
            'w'.$maxWindows,
        ]);
    }
}
