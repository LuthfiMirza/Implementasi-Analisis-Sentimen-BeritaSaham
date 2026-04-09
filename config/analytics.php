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
];
