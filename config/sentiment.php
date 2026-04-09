<?php

return [
    'engine' => env('SENTIMENT_ENGINE', 'hybrid'),
    'python_endpoint' => env('PYTHON_SENTIMENT_ENDPOINT'),
    'python_timeout' => env('PYTHON_SENTIMENT_TIMEOUT', 5),
];
