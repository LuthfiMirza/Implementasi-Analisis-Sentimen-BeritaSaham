<?php

namespace App\Console\Commands;

use App\Models\Stock;
use App\Services\PaperTrading\PaperTradingLogService;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

#[Signature('paper-trading:evaluate-result {--date=}')]
#[Description('Evaluate a paper trading snapshot against actual returns after the configured horizon')]
class EvaluatePaperTradingResult extends Command
{
    public function __construct(
        protected PaperTradingLogService $paperTradingLogService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $snapshotDate = (string) $this->option('date');
        if (trim($snapshotDate) === '') {
            $this->error('Gunakan --date=YYYY-MM-DD untuk memilih snapshot yang akan dievaluasi.');

            return self::FAILURE;
        }

        $path = $this->paperTradingLogService->snapshotPath($snapshotDate);
        if (! File::exists($path)) {
            $this->error("Snapshot tidak ditemukan: {$path}");

            return self::FAILURE;
        }

        $payload = json_decode((string) File::get($path), true);
        if (! is_array($payload) || ! isset($payload['rankings']) || ! is_array($payload['rankings'])) {
            $this->error('Format snapshot tidak valid.');

            return self::FAILURE;
        }

        $snapshotAnchorDate = (string) ($payload['date'] ?? $snapshotDate);
        $referenceDate = (string) ($payload['reference_date'] ?? '');
        $horizonDays = (int) ($payload['horizon_days'] ?? 5);
        if (trim($snapshotAnchorDate) === '') {
            $this->error('Snapshot belum memiliki tanggal dasar evaluasi.');

            return self::FAILURE;
        }

        $rows = [];
        $skipped = [];

        foreach ($payload['rankings'] as $entry) {
            $ticker = strtoupper((string) ($entry['ticker'] ?? ''));
            $snapshotPrice = $entry['price_at_snapshot'] ?? null;

            if (! $ticker || ! is_numeric($snapshotPrice) || (float) $snapshotPrice <= 0) {
                $skipped[] = $ticker ?: '(unknown)';
                continue;
            }

            $stock = Stock::where('code', $ticker)->first();
            if (! $stock) {
                $skipped[] = $ticker;
                continue;
            }

            $target = $this->paperTradingLogService->evaluationTargetForSnapshotDate($stock, $snapshotAnchorDate, $horizonDays);
            if (! $target) {
                $skipped[] = $ticker;
                continue;
            }

            $actualReturn = (((float) $target['price']) / ((float) $snapshotPrice)) - 1.0;

            $rows[] = [
                'ticker' => $ticker,
                'predicted_rank' => (int) ($entry['rank'] ?? 0),
                'predicted_score' => round((float) ($entry['score'] ?? 0), 4),
                'signal' => (string) ($entry['signal'] ?? 'neutral'),
                'snapshot_price' => round((float) $snapshotPrice, 4),
                'actual_price' => round((float) $target['price'], 4),
                'actual_return' => $actualReturn,
                'eval_date' => (string) $target['price_date'],
            ];
        }

        if (count($rows) < 2) {
            $this->error('Data evaluasi tidak cukup. Minimal dua ticker dengan harga aktual diperlukan.');

            return self::FAILURE;
        }

        usort($rows, function (array $left, array $right): int {
            $cmp = $right['actual_return'] <=> $left['actual_return'];
            if ($cmp !== 0) {
                return $cmp;
            }

            return $left['ticker'] <=> $right['ticker'];
        });

        foreach ($rows as $index => &$row) {
            $row['actual_rank'] = $index + 1;
        }
        unset($row);

        usort($rows, fn (array $left, array $right): int => $left['predicted_rank'] <=> $right['predicted_rank']);

        $spearman = $this->calculateSpearman($rows);
        $topK = min(3, count($rows));
        $topRows = array_slice($rows, 0, $topK);
        $bottomRows = array_slice($rows, -1 * $topK);
        $topAvg = array_sum(array_column($topRows, 'actual_return')) / $topK;
        $bottomAvg = array_sum(array_column($bottomRows, 'actual_return')) / $topK;
        $longShortSpreadPct = ($topAvg - $bottomAvg) * 100;

        $actualTopTickers = collect($rows)
            ->sortBy('actual_rank')
            ->take($topK)
            ->pluck('ticker')
            ->all();
        $predictedTopTickers = array_column($topRows, 'ticker');
        $top3Precision = count(array_intersect($predictedTopTickers, $actualTopTickers)) / $topK;
        $top1Hit = ($predictedTopTickers[0] ?? null) === ($actualTopTickers[0] ?? null) ? 1 : 0;
        $evalDate = collect($rows)->pluck('eval_date')->unique()->sort()->last();

        $notes = sprintf(
            'snapshot_anchor_date=%s; reference_date=%s; horizon_trading_days=%d; evaluated=%d; skipped=%d',
            $snapshotAnchorDate,
            $referenceDate ?: '-',
            $horizonDays,
            count($rows),
            count($skipped)
        );

        $this->upsertResultsRow([
            'snapshot_date' => $snapshotDate,
            'eval_date' => (string) $evalDate,
            'spearman' => $this->formatMetric($spearman),
            'long_short_spread' => $this->formatMetric($longShortSpreadPct),
            'top3_precision' => $this->formatMetric($top3Precision),
            'top1_hit' => (string) $top1Hit,
            'notes' => $notes,
        ]);

        $this->info("Evaluasi snapshot {$snapshotDate} berhasil.");
        $this->line("Eval date: {$evalDate}");
        $this->line('Spearman: '.$this->formatMetric($spearman));
        $this->line('Long-short spread (%): '.$this->formatMetric($longShortSpreadPct));
        $this->line('Top-3 precision: '.$this->formatMetric($top3Precision));
        $this->line('Top-1 hit: '.$top1Hit);
        if ($skipped !== []) {
            $this->warn('Skipped tickers: '.implode(', ', $skipped));
        }
        $this->table(
            ['Ticker', 'Pred Rank', 'Actual Rank', 'Snapshot', 'Actual', 'Return %'],
            collect($rows)->map(fn (array $row) => [
                $row['ticker'],
                $row['predicted_rank'],
                $row['actual_rank'],
                number_format((float) $row['snapshot_price'], 4, '.', ''),
                number_format((float) $row['actual_price'], 4, '.', ''),
                number_format($row['actual_return'] * 100, 4, '.', ''),
            ])->all()
        );

        return self::SUCCESS;
    }

    protected function calculateSpearman(array $rows): ?float
    {
        $n = count($rows);
        if ($n < 2) {
            return null;
        }

        $sumD2 = 0.0;
        foreach ($rows as $row) {
            $d = ((int) $row['predicted_rank']) - ((int) $row['actual_rank']);
            $sumD2 += $d * $d;
        }

        return 1 - ((6 * $sumD2) / ($n * (($n * $n) - 1)));
    }

    protected function upsertResultsRow(array $row): void
    {
        $this->paperTradingLogService->ensureOutputDirectory();
        $path = $this->paperTradingLogService->resultsCsvPath();
        $header = ['snapshot_date', 'eval_date', 'spearman', 'long_short_spread', 'top3_precision', 'top1_hit', 'notes'];

        $existing = [];
        if (File::exists($path)) {
            $lines = array_filter(array_map('trim', preg_split('/\r\n|\r|\n/', (string) File::get($path))));
            foreach ($lines as $index => $line) {
                $parsed = str_getcsv($line);
                if ($index === 0 || $parsed === []) {
                    continue;
                }
                $existing[] = array_combine($header, array_pad($parsed, count($header), ''));
            }
        }

        $replaced = false;
        foreach ($existing as $index => $existingRow) {
            if (($existingRow['snapshot_date'] ?? null) === $row['snapshot_date']) {
                $existing[$index] = $row;
                $replaced = true;
                break;
            }
        }

        if (! $replaced) {
            $existing[] = $row;
        }

        usort($existing, fn (array $left, array $right): int => strcmp($left['snapshot_date'], $right['snapshot_date']));

        $handle = fopen($path, 'wb');
        fputcsv($handle, $header);
        foreach ($existing as $record) {
            fputcsv($handle, array_map(fn (string $column) => $record[$column] ?? '', $header));
        }
        fclose($handle);
    }

    protected function formatMetric(?float $value): string
    {
        return $value === null ? '' : number_format($value, 6, '.', '');
    }
}
