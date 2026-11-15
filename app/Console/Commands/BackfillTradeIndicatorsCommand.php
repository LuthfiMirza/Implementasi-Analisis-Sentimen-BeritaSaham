<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Trade;
use App\Services\Trading\TradeQualityGraderService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;
use Throwable;

class BackfillTradeIndicatorsCommand extends Command
{
    protected $signature = 'trades:backfill-indicators {--only-missing : Hanya proses trade yang indicators_snapshot-nya masih kosong}';

    protected $description = 'Backfill indicators_snapshot, signal_quality (A+/A/B/C), dss_score, dan sentiment_avg untuk seluruh Trade di /trades (Fase FD-1)';

    public function handle(TradeQualityGraderService $grader): int
    {
        $query = Trade::orderBy('entry_date')->orderBy('id');
        if ($this->option('only-missing')) {
            $query->whereNull('indicators_snapshot');
        }

        $trades = $query->get();
        if ($trades->isEmpty()) {
            $this->info('Tidak ada trade yang perlu di-backfill.');

            return self::SUCCESS;
        }

        $this->info("Memproses backfill indikator & kualitas sinyal untuk {$trades->count()} trade...");

        $payload = $trades->map(fn (Trade $t) => [
            'id' => $t->id,
            'ticker' => $t->ticker ?: optional($t->stock)->code,
            'entry_date' => $t->entry_date?->format('Y-m-d'),
            'exit_date' => $t->exit_date?->format('Y-m-d'),
            'entry_price' => (float) $t->entry_price,
            'exit_price' => $t->exit_price !== null ? (float) $t->exit_price : null,
        ])->values()->all();

        $tmpIn = storage_path('app/tmp_trades_backfill_in.json');
        $tmpOut = storage_path('app/tmp_trades_backfill_out.json');

        file_put_contents($tmpIn, json_encode($payload, JSON_PRETTY_PRINT));

        $computedMap = [];
        $script = base_path('quant/drawdown_bounce_tracker/compute_trade_indicators.py');
        $python = env('PYTHON_BINARY', 'python3');

        if (is_file($script)) {
            $result = Process::timeout(180)->run([$python, $script, $tmpIn, $tmpOut]);
            if ($result->successful() && is_file($tmpOut)) {
                $decoded = json_decode((string) file_get_contents($tmpOut), true);
                if (is_array($decoded)) {
                    $computedMap = $decoded;
                }
            } else {
                $this->warn('Script compute_trade_indicators.py gagal/dilewati, menggunakan fallback internal: '.trim($result->errorOutput()));
            }
        }

        @unlink($tmpIn);
        @unlink($tmpOut);

        $updatedCount = 0;
        $gradeCounts = ['A+' => 0, 'A' => 0, 'B' => 0, 'C' => 0];

        Trade::withoutEvents(function () use ($trades, $computedMap, $grader, &$updatedCount, &$gradeCounts) {
            foreach ($trades as $trade) {
                $tid = (string) $trade->id;
                $existingSnap = is_array($trade->indicators_snapshot) ? $trade->indicators_snapshot : [];
                $pyInd = isset($computedMap[$tid]) && is_array($computedMap[$tid]) ? $computedMap[$tid] : [];
                $mergedInd = array_merge($existingSnap, $pyInd);

                $ticker = (string) ($trade->ticker ?: optional($trade->stock)->code ?: '');
                $graded = $grader->gradeTrade(
                    $ticker,
                    $trade->strategy_label,
                    $mergedInd,
                    $trade->notes
                );

                $sentimentAvg = $trade->sentiment_avg;
                if ($sentimentAvg === null && $trade->stock_id && $trade->entry_date) {
                    try {
                        $avgScore = NewsArticle::where('stock_id', $trade->stock_id)
                            ->whereNotNull('sentiment_score')
                            ->whereBetween('published_at', [
                                $trade->entry_date->copy()->subDays(14)->startOfDay(),
                                $trade->entry_date->copy()->endOfDay(),
                            ])
                            ->avg('sentiment_score');
                        if ($avgScore !== null) {
                            $sentimentAvg = round((float) $avgScore, 4);
                        }
                    } catch (Throwable $e) {
                        // Ignore if news lookup fails
                    }
                }

                $trade->update([
                    'signal_quality' => $graded['grade'],
                    'dss_score' => $graded['quality_score'],
                    'dss_status' => $graded['dss_status'],
                    'dss_prediction' => $graded['dss_prediction'],
                    'sentiment_avg' => $sentimentAvg,
                    'indicators_snapshot' => $graded['snapshot'],
                ]);

                $grade = $graded['grade'];
                if (isset($gradeCounts[$grade])) {
                    $gradeCounts[$grade]++;
                }
                $updatedCount++;
            }
        });

        $this->info(sprintf(
            'Selesai! %d trade diperbarui (Grade A+: %d | Grade A: %d | Grade B: %d | Grade C: %d).',
            $updatedCount,
            $gradeCounts['A+'],
            $gradeCounts['A'],
            $gradeCounts['B'],
            $gradeCounts['C']
        ));

        return self::SUCCESS;
    }
}

