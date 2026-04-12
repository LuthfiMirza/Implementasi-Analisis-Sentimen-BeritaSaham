<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Console\Scheduling\Schedule;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withCommands([
        \App\Console\Commands\FetchNewsCommand::class,
        \App\Console\Commands\AnalyzeSentimentCommand::class,
        \App\Console\Commands\UpdateStockSnapshotsCommand::class,
        \App\Console\Commands\GenerateEvaluationReport::class,
        \App\Console\Commands\SentimentComparisonCommand::class,
        \App\Console\Commands\SyncLivePricesCommand::class,
        \App\Console\Commands\NewsCoverageReportCommand::class,
        \App\Console\Commands\RescoreNewsQualityCommand::class,
        \App\Console\Commands\RescoreNewsSentimentCommand::class,
        \App\Console\Commands\FetchStockHistoryCommand::class,
    ])
    ->withSchedule(function (Schedule $schedule): void {
        // Fetch news multi-provider tiap 2 jam
        $schedule->command('news:fetch --limit=15')->everyTwoHours()->withoutOverlapping()->runInBackground();
        // Fetch RSS lokal lebih sering (sumber cepat)
        $schedule->command('news:fetch --provider=rss_local --limit=20')->hourly()->withoutOverlapping()->runInBackground();
        $schedule->command('news:analyze')->hourly();
        $schedule->command('stocks:update-snapshots')->dailyAt('16:15');
    })
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->alias([
            'admin' => \App\Http\Middleware\AdminMiddleware::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        //
    })->create();
