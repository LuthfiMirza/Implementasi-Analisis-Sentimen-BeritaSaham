<?php

return [
    'near_duplicate_threshold' => 0.92,
    'date_window_days' => 14,
    'grouping_version' => 'sentiment-groups-v1',
    'split_seed' => 42,
    'candidate_sizes' => [
        'candidate-a' => ['mode' => 'ratio', 'value' => 0.15],
        'candidate-b' => ['mode' => 'rows', 'value' => 250],
        'candidate-c' => ['mode' => 'rows', 'value' => 325],
    ],
    'allowed_labels' => ['positive', 'neutral', 'negative'],
    'official_test_version' => 'sentiment-test-v1',
    'validation_ratio' => 0.15,
    'hard_case_sample_method_patterns' => ['legacy_hard_case'],
    'sample_method_mapping' => [
        'representative_random' => 'population_random',
        'legacy_hard_case' => 'hard_case',
        '' => 'unknown',
    ],
    'excluded_conflict_status' => ['mixed_label_conflict'],
];
