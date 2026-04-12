<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\Api\QuoteController;

Route::get('/stocks/{code}/quote', [QuoteController::class, 'show']);
