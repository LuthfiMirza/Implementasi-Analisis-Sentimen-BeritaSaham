<?php

return [
    'rss_timeout' => env('NEWS_RSS_TIMEOUT', 8),
    'rss_user_agent' => env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'),

    'relevance_threshold' => env('NEWS_RELEVANCE_THRESHOLD', 0.35),
    'high_threshold' => env('NEWS_RELEVANCE_HIGH', 0.55),
    'final_quality_threshold' => env('NEWS_FINAL_QUALITY_THRESHOLD', 0.40),
    'quality_high' => env('NEWS_QUALITY_HIGH', 0.55),
    'quality_medium' => env('NEWS_QUALITY_MEDIUM', 0.40),
    'context_keywords' => [
        'saham', 'emiten', 'idx', 'bei', 'ihsg', 'dividen', 'laba', 'pendapatan',
        'rights issue', 'buyback', 'target harga', 'rekomendasi', 'obligasi', 'rights',
        'investor', 'kuartal', 'kinerja', 'profit', 'revenue', 'earnings', 'stock',
        'listed', 'exchange', 'market', 'ipo', 'rights issue', 'prospektus', 'dividend',
    ],
    'source_weights' => [
        'rss_local' => 1.0,
        'newsapi' => 0.95,
        'gnews' => 0.9,
        'finnhub' => 0.85,
        'gdelt' => 0.7,
        'mock' => 0.5,
    ],
    'source_priority' => ['rss_local', 'gnews', 'gdelt'],

    // Optional preferensi per saham: jika di-set, urutan provider akan mengikuti mapping ini ketika mode multi.
    'preferred_providers' => [
        // 'ASII' => ['newsapi', 'rss_local', 'gnews'],
        // 'ADRO' => ['newsapi', 'gnews', 'rss_local'],
        // 'GOTO' => ['newsapi', 'gnews', 'rss_local'],
    ],
];
