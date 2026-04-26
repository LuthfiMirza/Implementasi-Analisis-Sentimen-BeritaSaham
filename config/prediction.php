<?php

return [
    'engine' => env('PREDICTION_ENGINE', 'baseline'),
    'python_endpoint' => env('PYTHON_PREDICTION_ENDPOINT'),
    'ranking_endpoint' => env(
        'PYTHON_RANKING_ENDPOINT',
        env('PYTHON_PREDICTION_ENDPOINT')
            ? preg_replace('/\/predict$/', '/rank-stocks', env('PYTHON_PREDICTION_ENDPOINT'))
            : null
    ),
    'timeout' => env('PYTHON_PREDICTION_TIMEOUT', 6),
];
