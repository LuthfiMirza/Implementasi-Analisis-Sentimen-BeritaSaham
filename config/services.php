<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'key' => env('POSTMARK_API_KEY'),
    ],

    'resend' => [
        'key' => env('RESEND_API_KEY'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    'news' => [
        'provider' => env('NEWS_PROVIDER', 'mock'),
        'api_key' => env('NEWS_API_KEY'),
        'api_base_url' => env('NEWS_API_BASE_URL'),
        'language' => env('NEWS_API_LANGUAGE', 'id'),
        'timeout' => env('NEWS_API_TIMEOUT', 8),
        'user_agent' => env('NEWS_API_USER_AGENT', 'SentimenaNews/1.0'),
    ],

    'gnews' => [
        'api_key' => env('GNEWS_API_KEY'),
        'api_base_url' => env('GNEWS_BASE_URL', 'https://gnews.io/api/v4/search'),
        'language' => env('GNEWS_LANGUAGE', 'id'),
        'country' => env('GNEWS_COUNTRY', 'id'),
        'timeout' => env('GNEWS_TIMEOUT', 8),
        'user_agent' => env('GNEWS_USER_AGENT', 'SentimenaNews/1.0'),
    ],

    'finnhub' => [
        'api_key' => env('FINNHUB_API_KEY'),
        'news_base_url' => env('FINNHUB_BASE_URL', 'https://finnhub.io/api/v1/company-news'),
    ],

    'sentiment' => [
        'python_endpoint' => env('PYTHON_SENTIMENT_ENDPOINT'),
    ],

    'python_prediction' => [
        'endpoint' => env('PYTHON_PREDICTION_ENDPOINT', 'http://localhost:8001/predict'),
        'timeout' => env('PYTHON_PREDICTION_TIMEOUT', 5),
    ],

    'python_ranking' => [
        'endpoint' => env('PYTHON_RANKING_ENDPOINT', 'http://localhost:8001/rank-stocks'),
        'timeout' => env('PYTHON_RANKING_TIMEOUT', 5),
    ],

    'python_sentiment' => [
        'endpoint' => env('PYTHON_SENTIMENT_ENDPOINT', 'http://localhost:8001/sentiment'),
        'timeout' => env('PYTHON_SENTIMENT_TIMEOUT', 5),
    ],

];
