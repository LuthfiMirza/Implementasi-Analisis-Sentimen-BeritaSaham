<?php

return [
    'data_source' => env('STOCK_DATA_SOURCE', 'live'), // live|snapshot|dummy
    'provider' => env('LIVE_MARKET_PROVIDER', 'demo'),
    'base_url' => env('MARKET_DATA_BASE_URL'),
    'api_key' => env('MARKET_DATA_API_KEY'),
    'timeout' => env('MARKET_DATA_TIMEOUT', 8),
    'user_agent' => env('MARKET_DATA_USER_AGENT', 'SentimenaMarket/1.0'),
    'refresh_seconds' => env('MARKET_DATA_REFRESH_SECONDS', 60),
    'fallback_to_snapshot' => env('FALLBACK_TO_SNAPSHOT', true),
];
