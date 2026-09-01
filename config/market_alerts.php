<?php

return [
    // Interpreter + script for the IDX stock-summary scraper.
    'python_binary' => env('IDX_SCRAPE_PYTHON', base_path('quant/.venv-fundamentals/bin/python3')),
    'scrape_script' => base_path('quant/idx_market/fetch_stock_summary.py'),
    'scrape_timeout' => (int) env('IDX_SCRAPE_TIMEOUT', 90),

    // Minutes to cache the computed alert lists (keyed by trade date).
    'cache_minutes' => (int) env('MARKET_ALERTS_CACHE_MINUTES', 15),

    // Lookback window (trading days) for the volume moving average.
    'volume_lookback' => 20,

    // Thresholds for a row to qualify as an alert.
    'volume' => [
        'min_ratio' => 5.0,          // today's volume >= 5x the 20-day average (3x is routine noise)
        'min_value_rp' => 5_000_000_000, // and today's turnover >= Rp 5 B (a spike on an illiquid name isn't interesting)
        'limit' => 60,
    ],
    'gap' => [
        'min_gap_pct' => 5.0,         // |open vs previous close| >= 5%
        'min_move_pct' => 12.0,       // OR |close vs previous close| >= 12% (near ARA/ARB)
        'min_value_rp' => 10_000_000_000, // and turnover >= Rp 10 B -- IDX 3-5% daily moves are routine
        'limit' => 60,
    ],
    'foreign' => [
        // |net foreign| >= Rp 30 B (approx: net shares * close). Absolute rupiah only -- a big %
        // of a thin stock's turnover isn't market-relevant and just adds noise.
        'min_net_value_rp' => 30_000_000_000,
        'limit' => 60,
    ],
    'ownership' => [
        'min_foreign_pct_delta' => 1.0, // flag MoM foreign ownership shift >= 1 percentage point
        'limit' => 100,
    ],
];
