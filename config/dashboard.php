<?php

return [
    'default_stock' => 'BBCA',
    'stock_chart_mode' => env('STOCK_CHART_MODE', 'tradingview'),
    'tradingview_exchange' => env('TRADINGVIEW_DEFAULT_EXCHANGE', 'IDX'),
    'news_provider' => env('NEWS_PROVIDER', 'mock'),
];
