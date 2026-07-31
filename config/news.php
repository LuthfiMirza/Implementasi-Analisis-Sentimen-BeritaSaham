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
        'currents' => 0.9,
        'mock' => 0.5,
    ],
    // 'finnhub' intentionally excluded from these two lists (still registered in
    // NewsAggregationService's $fetchers so `--provider=finnhub` still works for manual testing).
    // Live-verified 2026-07-31: Finnhub's free tier rejects any '.JK'-suffixed IDX symbol with
    // "You don't have access to this resource" (403) -- confirmed by testing the same API key
    // successfully against a US ticker (AAPL, real data returned). Also confirmed stripping the
    // '.JK' suffix is NOT a safe workaround: "BBCA" without the suffix returns real Finnhub data,
    // but for an unrelated US-listed collision on that ticker symbol, not Bank Central Asia --
    // ingesting that would silently attribute wrong-company news. This is an account/plan
    // limitation, not fixable in code; every request against IDX tickers is guaranteed to fail.
    'multi_providers' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'ojk', 'gnews', 'newsapi', 'gdelt', 'currents'],
    'source_priority' => ['idx_disclosure', 'google_news_rss', 'business_site_search', 'rss_local', 'ojk', 'gnews', 'newsapi', 'gdelt', 'currents'],
    // Fase R7a: google_news_rss URLs are unresolvable (confirmed dead end -- Google now serves a
    // client-rendered SPA, no publisher URL in static HTML), so full_text can never be backfilled
    // for its share of articles. Shrinking its per-fetch limit and growing the sources that
    // already scrape at 96-100% shifts future article volume toward full_text-able sources
    // without touching google_news_rss's existing 1,349 stuck rows.
    'provider_limit_multiplier' => [
        'google_news_rss' => 0.3,
        'rss_local' => 1.5,
        'business_site_search' => 1.5,
        'ojk' => 1.2,
        'newsapi' => 1.5,
        'currents' => 1.5,
    ],
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
