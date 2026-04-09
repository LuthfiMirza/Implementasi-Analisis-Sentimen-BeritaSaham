<?php

return [
    'engine' => env('PREDICTION_ENGINE', 'baseline'),
    'python_endpoint' => env('PYTHON_PREDICTION_ENDPOINT'),
    'timeout' => env('PYTHON_PREDICTION_TIMEOUT', 6),
];
