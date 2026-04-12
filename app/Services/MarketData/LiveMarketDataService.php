<?php

namespace App\Services\MarketData;

use App\Models\Stock;
use App\Services\Stocks\PriceSeriesService;
use Illuminate\Support\Facades\Log;

class LiveMarketDataService
{
    public function __construct(
        protected ?MarketDataProviderInterface $provider = null,
        protected ?PriceSeriesService $snapshotService = null
    ) {
        $this->snapshotService ??= app(PriceSeriesService::class);
        $this->provider = $this->provider ?? $this->resolveProvider();
    }

    public function quote(Stock $stock): ?array
    {
        $dataSource = config('market.data_source', 'live');
        if ($dataSource === 'dummy') {
            return (new DemoMarketDataProvider())->quote($stock);
        }

        $quote = $dataSource === 'snapshot' ? null : $this->provider?->quote($stock);
        if ($quote) {
            return $quote;
        }

        if (config('market.fallback_to_snapshot', true)) {
            return $this->snapshotQuote($stock);
        }

        return null;
    }

    protected function resolveProvider(): MarketDataProviderInterface
    {
        $provider = config('market.provider', 'demo');
        if ($provider === 'demo') {
            return new DemoMarketDataProvider();
        }

        return new HttpMarketDataProvider();
    }

    protected function snapshotQuote(Stock $stock): ?array
    {
        $latest = $this->snapshotService->latestWithChange($stock);
        $snap = $latest['latest'];
        $prev = $latest['previous'];

        if (! $snap) {
            Log::info('Snapshot quote not available', ['stock' => $stock->code]);
            return null;
        }

        $change = null;
        $changePct = null;
        if ($prev && $prev->close) {
            $change = $snap->close - $prev->close;
            $changePct = ($change / $prev->close) * 100;
        }

        return [
            'stock_code' => $stock->code,
            'open' => $snap->open,
            'high' => $snap->high,
            'low' => $snap->low,
            'close' => $snap->close,
            'last' => $snap->close,
            'volume' => $snap->volume,
            'change' => $change,
            'change_percent' => $changePct !== null ? round($changePct, 4) : null,
            'source' => 'backend_snapshot',
            'is_live' => false,
            'fetched_at' => $snap->price_date,
        ];
    }
}
