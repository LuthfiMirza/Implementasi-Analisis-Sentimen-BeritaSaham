<?php

namespace App\Services\MarketData;

use App\Models\Stock;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class HttpMarketDataProvider implements MarketDataProviderInterface
{
    public function quote(Stock $stock): ?array
    {
        $baseUrl = config('market.base_url');
        $timeout = config('market.timeout', 8);
        $ua = config('market.user_agent', 'Mozilla/5.0');

        if (! $baseUrl) {
            return null;
        }

        try {
            $url = rtrim($baseUrl, '/').'/'.$stock->code.'.JK';
            $resp = Http::withHeaders([
                'User-Agent' => $ua,
                'Accept' => 'application/json',
            ])->timeout($timeout)->get($url, [
                'interval' => '1d',
                'range' => '1d',
            ]);

            if (! $resp->successful()) {
                Log::warning('MarketData HTTP failed', ['status' => $resp->status(), 'body' => $resp->body()]);
                return null;
            }

            $data = $resp->json();
            if (! is_array($data)) {
                return null;
            }

            return $this->mapPayload($stock, $data);
        } catch (\Throwable $e) {
            Log::warning('MarketData HTTP exception', ['error' => $e->getMessage()]);
            return null;
        }
    }

    protected function mapPayload(Stock $stock, array $data): ?array
    {
        // Yahoo Finance v8 chart: nested chart.result[0].meta + indicators.quote[0]
        if (isset($data['chart']['error']) && $data['chart']['error']) {
            return null;
        }

        $result = $data['chart']['result'][0] ?? null;
        if (! $result) {
            return null;
        }

        $meta = $result['meta'] ?? [];
        $quote = $result['indicators']['quote'][0] ?? [];

        $open = $quote['open'][0] ?? ($meta['regularMarketPrice'] ?? null);
        $high = $quote['high'][0] ?? ($meta['regularMarketDayHigh'] ?? null);
        $low = $quote['low'][0] ?? ($meta['regularMarketDayLow'] ?? null);
        $close = $quote['close'][0] ?? ($meta['regularMarketPrice'] ?? null);
        $volume = $quote['volume'][0] ?? ($meta['regularMarketVolume'] ?? null);
        $prev = $meta['chartPreviousClose'] ?? null;

        if ($close === null) {
            return null;
        }

        $change = ($close && $prev) ? round($close - $prev, 2) : null;
        $changePercent = ($close && $prev && $prev > 0)
            ? round((($close - $prev) / $prev) * 100, 4)
            : null;

        return [
            'stock_code' => $stock->code,
            'open' => $open !== null ? (float) $open : null,
            'high' => $high !== null ? (float) $high : null,
            'low' => $low !== null ? (float) $low : null,
            'close' => (float) $close,
            'last' => (float) $close,
            'volume' => $volume !== null ? (int) $volume : null,
            'change' => $change,
            'change_percent' => $changePercent !== null ? round($changePercent, 4) : null,
            'source' => 'yahoo_finance',
            'is_live' => true,
            'fetched_at' => now()->toISOString(),
        ];
    }
}
