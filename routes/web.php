<?php

use App\Http\Controllers\Admin\NewsArticleController as AdminNewsArticleController;
use App\Http\Controllers\Admin\NewsController as AdminNewsController;
use App\Http\Controllers\Admin\NewsSourceController as AdminNewsSourceController;
use App\Http\Controllers\Admin\StockController as AdminStockController;
use App\Http\Controllers\Admin\SystemController as AdminSystemController;
use App\Http\Controllers\Admin\UserController as AdminUserController;
use App\Http\Controllers\AnalyticsController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\EvaluasiController;
use App\Http\Controllers\TradeController;
use App\Http\Controllers\TradeJournalController;
use App\Http\Controllers\BacktestController;
use App\Http\Controllers\NewsController;
use App\Http\Controllers\ProfileController;
use App\Http\Controllers\SearchController;
use App\Http\Controllers\SentimentValidationController;
use App\Http\Controllers\StockController;
use App\Http\Controllers\WatchlistController;
use Illuminate\Support\Facades\Route;

Route::get('/', fn () => redirect()->route('dashboard'));

Route::middleware(['auth', 'verified'])->group(function () {
    Route::get('/dashboard', [DashboardController::class, 'index'])->name('dashboard');
    Route::get('/universal-search', SearchController::class)->name('search.universal');
    Route::get('/stocks/search', [StockController::class, 'search'])->name('stocks.search');
    Route::get('/stocks/{code}', [StockController::class, 'show'])->name('stocks.show');
    Route::get('/watchlist', [WatchlistController::class, 'index'])->name('watchlist.index');
    Route::post('/watchlist', [WatchlistController::class, 'store'])->name('watchlist.store');
    Route::delete('/watchlist/{stock}', [WatchlistController::class, 'destroy'])->name('watchlist.destroy');
    Route::get('/analytics', [AnalyticsController::class, 'index'])->name('analytics.index');
    Route::get('/news', [NewsController::class, 'index'])->name('news.index');
    Route::get('/sentiment-validation', [SentimentValidationController::class, 'index'])->name('sentiment-validation.index');
    Route::get('/sentiment-validation/next', [SentimentValidationController::class, 'next'])->name('sentiment-validation.next');
    Route::get('/sentiment-validation/active-learning', [SentimentValidationController::class, 'activeLearning'])->name('sentiment-validation.active-learning');
    Route::get('/sentiment-validation/active-learning/next', [SentimentValidationController::class, 'activeLearningNext'])->name('sentiment-validation.active-learning.next');
    Route::get('/sentiment-validation/representative', [SentimentValidationController::class, 'representativeSample'])->name('sentiment-validation.representative');
    Route::get('/sentiment-validation/representative/next', [SentimentValidationController::class, 'representativeSampleNext'])->name('sentiment-validation.representative.next');
    Route::post('/sentiment-validation/label', [SentimentValidationController::class, 'store'])->name('sentiment-validation.store');
    Route::get('/sentiment-validation/summary', [SentimentValidationController::class, 'summary'])->name('sentiment-validation.summary');
    Route::get('/evaluasi', [EvaluasiController::class, 'index'])->name('evaluasi.index');
    Route::get('/evaluasi/sentimen', [EvaluasiController::class, 'sentimen'])->name('evaluasi.sentimen');
    Route::get('/evaluasi/{code}', [EvaluasiController::class, 'show'])->name('evaluasi.show');
    Route::get('/trades', [TradeController::class, 'index'])->name('trades.index');
    Route::get('/trades/live', [TradeController::class, 'live'])->name('trades.live');
    Route::get('/trades/live-data', [TradeController::class, 'liveData'])->name('trades.live-data');
    Route::get('/trades/radar', [TradeController::class, 'radar'])->name('trades.radar');
    Route::get('/trades/radar-data', [TradeController::class, 'radarData'])->name('trades.radar-data');
    Route::get('/trades/laporan', [TradeController::class, 'laporan'])->name('trades.laporan');
    Route::post('/trades', [TradeController::class, 'store'])->name('trades.store');
    Route::post('/trades/position-sizing', [TradeController::class, 'updatePositionSizing'])->name('trades.position-sizing');
    Route::post('/trades/{trade}/close', [TradeController::class, 'close'])->name('trades.close');
    Route::delete('/trades/{trade}', [TradeController::class, 'destroy'])->name('trades.destroy');
    Route::prefix('trade-journal')->name('trade-journal.')->group(function () {
        Route::get('/', [TradeJournalController::class, 'index'])->name('index');
        Route::get('/create', [TradeJournalController::class, 'create'])->name('create');
        Route::post('/', [TradeJournalController::class, 'store'])->name('store');
        Route::get('/{trade}/edit', [TradeJournalController::class, 'edit'])->name('edit');
        Route::patch('/{trade}', [TradeJournalController::class, 'update'])->name('update');
        Route::delete('/{trade}', [TradeJournalController::class, 'destroy'])->name('destroy');
        Route::patch('/{trade}/close', [TradeJournalController::class, 'close'])->name('close');
    });
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
        Route::resource('users', AdminUserController::class)->except(['show', 'create', 'store']);
        Route::patch('stocks/{stock}/fundamental', [AdminStockController::class, 'updateFundamental'])->name('stocks.fundamental.update');
        Route::resource('stocks', AdminStockController::class);
        Route::resource('news', AdminNewsController::class)->only(['index', 'show', 'destroy']);
        Route::resource('news-sources', AdminNewsSourceController::class);
        Route::resource('news-articles', AdminNewsArticleController::class);
        Route::post('system', [AdminSystemController::class, 'update'])->name('system.update');
    });

require __DIR__.'/auth.php';
