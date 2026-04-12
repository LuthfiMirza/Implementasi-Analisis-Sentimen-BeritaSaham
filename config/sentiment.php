<?php

return [
    'engine' => env('SENTIMENT_ENGINE', 'hybrid'),
    'python_endpoint' => env('PYTHON_SENTIMENT_ENDPOINT'),
    'python_timeout' => env('PYTHON_SENTIMENT_TIMEOUT', 15),
    'huggingface_token' => env('HUGGINGFACE_API_TOKEN'),
];
