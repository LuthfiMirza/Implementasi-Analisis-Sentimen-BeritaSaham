<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\Api\ApiPredictionController;
use App\Http\Controllers\Api\QuoteController;

Route::get('/stocks/{code}/quote', [QuoteController::class, 'show']);
Route::post('/predict', [ApiPredictionController::class, 'predict']);
Route::post('/rank-stocks', [ApiPredictionController::class, 'rankStocks']);
