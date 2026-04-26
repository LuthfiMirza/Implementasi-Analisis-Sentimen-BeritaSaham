<?php

namespace App\Console\Commands;

use App\Services\PaperTrading\PaperTradingLogService;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

#[Signature('paper-trading:summarize')]
#[Description('Summarize paper trading evaluation results against the backtest target')]
class SummarizePaperTrading extends Command
{
    public function __construct(
        protected PaperTradingLogService $paperTradingLogService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $path = $this->paperTradingLogService->resultsCsvPath();
        if (! File::exists($path)) {
            $this->warn('Belum ada results_log.csv untuk diringkas.');

            return self::SUCCESS;
        }

        $header = ['snapshot_date', 'eval_date', 'spearman', 'long_short_spread', 'top3_precision', 'top1_hit', 'notes'];
        $rows = [];
        $lines = array_filter(array_map('trim', preg_split('/\r\n|\r|\n/', (string) File::get($path))));
        foreach ($lines as $index => $line) {
            $parsed = str_getcsv($line);
            if ($index === 0 || $parsed === []) {
                continue;
            }

            $row = array_combine($header, array_pad($parsed, count($header), ''));
            $rows[] = [
                'snapshot_date' => $row['snapshot_date'],
                'eval_date' => $row['eval_date'],
                'spearman' => $row['spearman'] !== '' ? (float) $row['spearman'] : null,
                'long_short_spread' => $row['long_short_spread'] !== '' ? (float) $row['long_short_spread'] : null,
                'top3_precision' => $row['top3_precision'] !== '' ? (float) $row['top3_precision'] : null,
                'top1_hit' => $row['top1_hit'] !== '' ? (int) $row['top1_hit'] : null,
                'notes' => $row['notes'] ?? '',
            ];
        }

        if ($rows === []) {
            $this->warn('results_log.csv ada, tetapi belum berisi siklus evaluasi.');

            return self::SUCCESS;
        }

        $cycles = count($rows);
        $avgSpearman = $this->average(array_column($rows, 'spearman'));
        $avgSpread = $this->average(array_column($rows, 'long_short_spread'));
        $avgTop3Precision = $this->average(array_column($rows, 'top3_precision'));
        $top1HitRate = $this->average(array_map(fn ($row) => $row['top1_hit'], $rows));

        $targetSpearman = 0.037;
        $targetSpread = 0.261;

        $this->info('Paper trading summary');
        $this->line('Total siklus dievaluasi: '.$cycles);
        $this->line('Average Spearman: '.$this->formatMetric($avgSpearman));
        $this->line('Average long-short spread (%): '.$this->formatMetric($avgSpread));
        $this->line('Top-3 precision keseluruhan: '.$this->formatMetric($avgTop3Precision));
        $this->line('Top-1 hit rate keseluruhan: '.$this->formatMetric($top1HitRate));
        $this->line('');
        $this->line('Benchmark backtest target');
        $this->line('Spearman target: '.number_format($targetSpearman, 6, '.', ''));
        $this->line('Long-short spread target (%): '.number_format($targetSpread, 6, '.', ''));
        $this->line('Delta Spearman: '.$this->formatMetric($avgSpearman !== null ? $avgSpearman - $targetSpearman : null));
        $this->line('Delta spread (%): '.$this->formatMetric($avgSpread !== null ? $avgSpread - $targetSpread : null));

        return self::SUCCESS;
    }

    protected function average(array $values): ?float
    {
        $filtered = array_values(array_filter($values, fn ($value) => $value !== null && $value !== ''));
        if ($filtered === []) {
            return null;
        }

        return array_sum($filtered) / count($filtered);
    }

    protected function formatMetric(?float $value): string
    {
        return $value === null ? '-' : number_format($value, 6, '.', '');
    }
}
