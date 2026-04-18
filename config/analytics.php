<?php

return [
    'source_weights' => [
        'finnhub' => 1.05,
        'newsapi' => 1.0,
        'gdelt' => 1.0,
        'rss_local' => 0.95,
        'manual' => 1.0,
        'mock' => 0.9,
    ],
    'headline_bonus' => 0.25,
    'recency_decay' => 0.4,
    'event_threshold' => 0.35,
    'macro_regulatory_signal' => [
        'enabled' => env('MACRO_REGULATORY_SIGNAL_ENABLED', true),
        'providers' => ['ojk_rss'],
        'watch_recent_7d_count' => 2,
        'overhang_recent_3d_count' => 2,
        'neutral_share_threshold' => 0.7,
        'min_confidence_multiplier' => 0.7,
        'min_score_multiplier' => 0.82,
        'confidence_penalty_scale' => 0.28,
        'score_penalty_scale' => 0.18,
        'threshold_tightening_scale' => 0.12,
    ],
    'phase_a_closeout' => [
        'baseline_status_min' => 'provisional',
        'min_ojk_article_count' => 5,
        'min_historical_days' => 30,
    ],
];
