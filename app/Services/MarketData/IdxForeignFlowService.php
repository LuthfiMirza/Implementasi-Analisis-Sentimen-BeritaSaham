<?php

namespace App\Services\MarketData;

use Illuminate\Support\Facades\Cache;
use Symfony\Component\Process\Process;
use Throwable;

class IdxForeignFlowService
{
    /**
     * Fetch and summarize 5-day official IDX Foreign Flow via local `idx` CLI JSON.
     * Cached for 30 minutes per ticker; gracefully returns null on timeout/offline.
     *
     * @return ?array<string, mixed>
     */
    public function summarize(string $ticker, int $days = 5): ?array
    {
        $code = strtoupper(trim($ticker));
        if ($code === '' || app()->runningUnitTests()) {
            return null;
        }

        return Cache::store('file')->remember("idx:foreign-flow:{$days}d:{$code}:v1", now()->addMinutes(30), function () use ($code, $days) {
            $bin = $this->resolveBinary();
            if ($bin === null) {
                return null;
            }

            try {
                $process = new Process([$bin, '-q', '-o', 'json', 'stocks', 'foreign', $code, '--days', (string) $days]);
                $process->setTimeout(6);
                $process->run();

                if (! $process->isSuccessful()) {
                    return null;
                }

                $decoded = json_decode($process->getOutput(), true);
                if (! is_array($decoded)) {
                    return null;
                }

                return $this->parseForeignPayload($decoded);
            } catch (Throwable) {
                return null;
            }
        });
    }

    /**
     * Batch summarize foreign flow for a list of tickers (each cached 30m independently).
     *
     * @param  list<string>  $tickers
     * @return array<string, ?array<string, mixed>>
     */
    public function summarizeBatch(array $tickers, int $days = 5): array
    {
        $out = [];
        foreach (array_unique(array_filter(array_map(fn ($t) => strtoupper(trim((string) $t)), $tickers))) as $tk) {
            $out[$tk] = $this->summarize($tk, $days);
        }

        return $out;
    }

    /**
     * Parse an `idx.foreign.v1` JSON payload into normalized Sentimena telemetry + UI badge.
     *
     * @param  array<string, mixed>  $payload
     * @return ?array<string, mixed>
     */
    public function parseForeignPayload(array $payload): ?array
    {
        $rows = $payload['data']['days'] ?? null;
        if (! is_array($rows) || count($rows) === 0) {
            return null;
        }

        // Ensure chronological order (oldest -> newest)
        usort($rows, fn (array $a, array $b) => strcmp((string) ($a['date'] ?? ''), (string) ($b['date'] ?? '')));

        $net5dRp = 0.0;
        $buyDays = 0;
        $sellDays = 0;

        foreach ($rows as $row) {
            $netVal = (float) ($row['foreign_net_value_at_close'] ?? 0);
            $net5dRp += $netVal;
            if ($netVal > 0) {
                $buyDays++;
            } elseif ($netVal < 0) {
                $sellDays++;
            }
        }

        $latest = $rows[count($rows) - 1];
        $net1dRp = (float) ($latest['foreign_net_value_at_close'] ?? 0);
        $latestDate = (string) ($latest['date'] ?? '');
        $sessions = count($rows);

        if ($net5dRp > 0 && $buyDays >= 3) {
            $status = 'FOREIGN_ACCUM';
            $label = '🟢 Asing Akumulasi';
            $badgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 font-semibold';
        } elseif ($net1dRp >= 5_000_000_000) {
            $status = 'FOREIGN_REVERSAL';
            $label = '🟢 Asing Masuk 1D';
            $badgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 font-semibold';
        } elseif ($net5dRp < 0 && $sellDays >= 3) {
            $status = 'FOREIGN_DIST';
            $label = '🔴 Asing Distribusi';
            $badgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/40 font-semibold';
        } else {
            $status = 'NEUTRAL';
            $label = '⚪ Asing Netral';
            $badgeClass = 'bg-slate-800/70 text-slate-300 border-slate-700/70';
        }

        return [
            'status' => $status,
            'label' => $label,
            'badge_class' => $badgeClass,
            'latest_date' => $latestDate,
            'sessions' => $sessions,
            'buy_days' => $buyDays,
            'sell_days' => $sellDays,
            'net_1d_rp' => round($net1dRp, 0),
            'net_5d_rp' => round($net5dRp, 0),
            'net_1d_formatted' => $this->formatRupiahShort($net1dRp),
            'net_5d_formatted' => $this->formatRupiahShort($net5dRp),
            'summary_text' => sprintf(
                '5D %s (%d/%d buy) • 1D %s',
                $this->formatRupiahShort($net5dRp),
                $buyDays,
                $sessions,
                $this->formatRupiahShort($net1dRp)
            ),
        ];
    }

    public function formatRupiahShort(float $amount): string
    {
        $sign = $amount > 0 ? '+' : ($amount < 0 ? '-' : '');
        $abs = abs($amount);

        if ($abs >= 1_000_000_000_000) {
            return $sign . 'Rp' . number_format($abs / 1_000_000_000_000, 2, ',', '.') . 'T';
        }
        if ($abs >= 1_000_000_000) {
            return $sign . 'Rp' . number_format($abs / 1_000_000_000, 1, ',', '.') . 'M';
        }
        if ($abs >= 1_000_000) {
            return $sign . 'Rp' . number_format($abs / 1_000_000, 0, ',', '.') . 'Jt';
        }

        return $sign . 'Rp' . number_format($abs, 0, ',', '.');
    }

    private function resolveBinary(): ?string
    {
        $candidates = array_filter([
            config('services.idx_cli.binary'),
            env('IDX_CLI_BINARY'),
            (getenv('HOME') ?: '/Users/mac') . '/.local/bin/idx',
            '/Users/mac/.local/bin/idx',
            '/usr/local/bin/idx',
            '/opt/homebrew/bin/idx',
        ]);

        foreach ($candidates as $path) {
            if (is_string($path) && is_executable($path)) {
                return $path;
            }
        }

        return null;
    }
}
