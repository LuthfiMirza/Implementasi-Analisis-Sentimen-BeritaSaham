<?php

return [
    'rss_timeout' => env('NEWS_RSS_TIMEOUT', 8),
    'rss_user_agent' => env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)'),
    'ojk_max_age_days' => env('NEWS_OJK_MAX_AGE_DAYS', 365),
    'ojk_backfill_candidate_limit' => env('NEWS_OJK_BACKFILL_CANDIDATE_LIMIT', 200),
    'ojk_backfill_max_pages' => env('NEWS_OJK_BACKFILL_MAX_PAGES', 18),

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
        'ojk_rss' => 1.1,
        'idx_disclosure' => 1.1,
        'business_site_search' => 1.0,
        'google_news_rss' => 0.95,
        'rss_local' => 1.0,
        'newsapi' => 0.95,
        'gnews' => 0.9,
        'finnhub' => 0.85,
        'gdelt' => 0.7,
        'mock' => 0.5,
    ],
    'multi_providers' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'ojk', 'gnews', 'newsapi', 'finnhub', 'gdelt'],
    'source_priority' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'ojk', 'gnews', 'newsapi', 'finnhub', 'gdelt'],
    'macro_global_providers' => ['ojk_rss'],
    'google_news_rss' => [
        'base_url' => env('NEWS_GOOGLE_RSS_BASE_URL', 'https://news.google.com/rss/search'),
        'hl' => env('NEWS_GOOGLE_RSS_HL', 'id'),
        'gl' => env('NEWS_GOOGLE_RSS_GL', 'ID'),
        'ceid' => env('NEWS_GOOGLE_RSS_CEID', 'ID:id'),
        'timeout' => env('NEWS_GOOGLE_RSS_TIMEOUT', 8),
        'user_agent' => env('NEWS_GOOGLE_RSS_USER_AGENT', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)')),
    ],
    'idx_disclosure' => [
        'calendar_url' => env('NEWS_IDX_DISCLOSURE_CALENDAR_URL', 'https://www.idx.id/en/listed-companies/listed-company-calendar/'),
        'timeout' => env('NEWS_IDX_DISCLOSURE_TIMEOUT', 8),
        'user_agent' => env('NEWS_IDX_DISCLOSURE_USER_AGENT', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)')),
    ],
    'business_site_search' => [
        'timeout' => env('NEWS_BUSINESS_SITE_SEARCH_TIMEOUT', 8),
        'user_agent' => env('NEWS_BUSINESS_SITE_SEARCH_USER_AGENT', env('NEWS_RSS_USER_AGENT', 'SentimenaBot/1.0 (+https://sentimena.app)')),
    ],

    // Optional preferensi per saham: jika di-set, urutan provider akan mengikuti mapping ini ketika mode multi.
    'preferred_providers' => [
        'UNVR' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'gnews', 'newsapi', 'finnhub', 'gdelt'],
        'ICBP' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'gnews', 'newsapi', 'finnhub', 'gdelt'],
    ],
];
