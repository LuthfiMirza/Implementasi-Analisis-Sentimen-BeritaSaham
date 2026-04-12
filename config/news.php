<?php

return [
    'rss_timeout' => env('NEWS_RSS_TIMEOUT', 8),
    'rss_user_agent' => env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'),

    'relevance_threshold' => env('NEWS_RELEVANCE_THRESHOLD', 0.25),
    'high_threshold' => env('NEWS_RELEVANCE_HIGH', 0.6),
    'final_quality_threshold' => env('NEWS_FINAL_QUALITY_THRESHOLD', 0.35),
    'quality_high' => env('NEWS_QUALITY_HIGH', 0.7),
    'quality_medium' => env('NEWS_QUALITY_MEDIUM', 0.5),
    'context_keywords' => [
        'saham', 'emiten', 'idx', 'bei', 'ihsg', 'dividen', 'laba', 'pendapatan',
        'rights issue', 'buyback', 'target harga', 'rekomendasi', 'obligasi', 'rights',
        'investor', 'kuartal', 'kinerja', 'profit', 'revenue', 'earnings', 'stock',
        'listed', 'exchange', 'market', 'ipo', 'rights issue', 'prospektus', 'dividend',
    ],
    'source_weights' => [
        'newsapi' => 1.0,
        'gnews' => 0.95,
        'rss_local' => 0.8,
        'gdelt' => 0.7,
        'finnhub' => 0.85,
        'mock' => 0.5,
    ],
    'source_priority' => ['newsapi', 'gnews', 'rss_local', 'gdelt', 'finnhub'],
];
