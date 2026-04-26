<?php

namespace App\Console\Commands;

use App\Services\PaperTrading\PaperTradingLogService;
use App\Services\Prediction\ResearchRankingService;
use Carbon\Carbon;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

#[Signature('paper-trading:record-snapshot {--date=}')]
#[Description('Record daily paper trading ranking snapshot for active watchlist tickers')]
class RecordPaperTradingSnapshot extends Command
{
    public function __construct(
        protected ResearchRankingService $researchRankingService,
        protected PaperTradingLogService $paperTradingLogService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $snapshotDate = $this->resolveSnapshotDate();
        $watchlistStocks = $this->paperTradingLogService->activeWatchlistStocks();
        $stocks = $this->paperTradingLogService->rankableWatchlistStocks();

        if ($watchlistStocks->count() < 2) {
            $this->error('Active watchlist membutuhkan minimal dua ticker untuk membuat snapshot ranking.');

            return self::FAILURE;
        }

        $excludedTickers = $watchlistStocks
            ->pluck('code')
            ->diff($stocks->pluck('code'))
            ->values()
            ->all();

        if ($stocks->count() < 2) {
            $this->error('Ticker watchlist yang memiliki feature series belum cukup untuk membuat snapshot ranking.');
            if ($excludedTickers !== []) {
                $this->warn('Ticker tanpa coverage feature: '.implode(', ', $excludedTickers));
            }

            return self::FAILURE;
        }

        $ranking = $this->researchRankingService->getRanking($stocks->pluck('code')->all());
        if (! ($ranking['available'] ?? false)) {
            $this->error((string) ($ranking['message'] ?? 'Ranking v5 tidak tersedia saat ini.'));

            return self::FAILURE;
        }

        $ranked = collect($ranking['ranked'] ?? []);
        if ($ranked->isEmpty()) {
            $this->error('Ranking v5 tidak mengembalikan data ticker.');

            return self::FAILURE;
        }

        $byCode = $stocks->keyBy(fn ($stock) => strtoupper($stock->code));
        $rankings = $ranked->map(function (array $row) use ($byCode): array {
            $stock = $byCode->get(strtoupper((string) ($row['ticker'] ?? '')));
            $price = $stock ? $this->paperTradingLogService->resolveSnapshotPrice($stock) : null;

            return [
                'ticker' => strtoupper((string) ($row['ticker'] ?? '')),
                'rank' => (int) ($row['rank'] ?? 0),
                'score' => round((float) ($row['score'] ?? 0), 4),
                'signal' => (string) ($row['signal'] ?? 'neutral'),
                'price_at_snapshot' => $price,
            ];
        })->values();

        $payload = [
            'date' => $snapshotDate->toDateString(),
            'reference_date' => (string) ($ranking['reference_date'] ?? ''),
            'rankings' => $rankings->all(),
            'model_version' => (string) ($ranking['model_version'] ?? 'v5_ranking'),
            'horizon_days' => (int) ($ranking['horizon_days'] ?? 5),
        ];

        $this->paperTradingLogService->ensureOutputDirectory();
        $path = $this->paperTradingLogService->snapshotPath($snapshotDate->toDateString());
        File::put($path, json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

        $this->info('Snapshot paper trading berhasil disimpan.');
        $this->line("Path: {$path}");
        $this->line('Reference date: '.($payload['reference_date'] ?: '-'));
        $this->line('Ticker count: '.$rankings->count());
        if ($excludedTickers !== []) {
            $this->warn('Ticker tanpa coverage feature dikeluarkan dari snapshot: '.implode(', ', $excludedTickers));
        }
        $this->table(
            ['Ticker', 'Rank', 'Score', 'Signal', 'Price'],
            $rankings->map(fn (array $row) => [
                $row['ticker'],
                $row['rank'],
                number_format((float) $row['score'], 4, '.', ''),
                $row['signal'],
                $row['price_at_snapshot'] !== null ? number_format((float) $row['price_at_snapshot'], 4, '.', '') : '-',
            ])->all()
        );

        return self::SUCCESS;
    }

    protected function resolveSnapshotDate(): Carbon
    {
        $raw = $this->option('date');

        if (is_string($raw) && trim($raw) !== '') {
            return Carbon::parse($raw, PaperTradingLogService::BUSINESS_TIMEZONE)->startOfDay();
        }

        return $this->paperTradingLogService->businessToday()->startOfDay();
    }
}
