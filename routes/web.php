<?php

use App\Http\Controllers\Admin\NewsArticleController as AdminNewsArticleController;
use App\Http\Controllers\Admin\NewsSourceController as AdminNewsSourceController;
use App\Http\Controllers\Admin\StockController as AdminStockController;
use App\Http\Controllers\Admin\SystemController as AdminSystemController;
use App\Http\Controllers\AnalyticsController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\EvaluasiController;
use App\Http\Controllers\EvaluationController;
use App\Http\Controllers\TradeController;
use App\Http\Controllers\BacktestController;
use App\Http\Controllers\NewsController;
use App\Http\Controllers\ProfileController;
use App\Http\Controllers\StockController;
use App\Http\Controllers\WatchlistController;
use Illuminate\Support\Facades\Route;

Route::get('/', fn () => redirect()->route('dashboard'));

Route::middleware(['auth', 'verified'])->group(function () {
    Route::get('/dashboard', [DashboardController::class, 'index'])->name('dashboard');
    Route::get('/stocks/search', [StockController::class, 'search'])->name('stocks.search');
    Route::get('/stocks/{code}', [StockController::class, 'show'])->name('stocks.show');
    Route::get('/watchlist', [WatchlistController::class, 'index'])->name('watchlist.index');
    Route::post('/watchlist', [WatchlistController::class, 'store'])->name('watchlist.store');
    Route::delete('/watchlist/{stock}', [WatchlistController::class, 'destroy'])->name('watchlist.destroy');
    Route::get('/analytics', [AnalyticsController::class, 'index'])->name('analytics.index');
    Route::get('/news', [NewsController::class, 'index'])->name('news.index');
    Route::get('/evaluasi', [EvaluasiController::class, 'index'])->name('evaluasi.index');
    Route::get('/evaluasi/sentimen', [EvaluasiController::class, 'sentimen'])->name('evaluasi.sentimen');
    Route::get('/evaluasi/{code}', [EvaluasiController::class, 'show'])->name('evaluasi.show');
    Route::get('/evaluation', [EvaluationController::class, 'index'])->name('evaluation.index');
    Route::get('/trades', [TradeController::class, 'index'])->name('trades.index');
    Route::post('/trades', [TradeController::class, 'store'])->name('trades.store');
    Route::post('/trades/{trade}/close', [TradeController::class, 'close'])->name('trades.close');
    Route::delete('/trades/{trade}', [TradeController::class, 'destroy'])->name('trades.destroy');
    Route::post('/api/news/refresh/{code}', [NewsController::class, 'refresh'])->name('news.refresh');
    Route::get('/backtest', [BacktestController::class, 'index'])->name('backtest.index');
    Route::get('/backtest/all', [BacktestController::class, 'all'])->name('backtest.all');

    Route::get('/profile', [ProfileController::class, 'edit'])->name('profile.edit');
    Route::patch('/profile', [ProfileController::class, 'update'])->name('profile.update');
    Route::delete('/profile', [ProfileController::class, 'destroy'])->name('profile.destroy');
});

Route::prefix('admin')
    ->middleware(['auth', 'admin'])
    ->name('admin.')
    ->group(function () {
        Route::get('/', [AdminSystemController::class, 'index'])->name('index');
        Route::resource('stocks', AdminStockController::class);
        Route::resource('news-sources', AdminNewsSourceController::class);
        Route::resource('news-articles', AdminNewsArticleController::class);
        Route::post('system', [AdminSystemController::class, 'update'])->name('system.update');
    });

require __DIR__.'/auth.php';
