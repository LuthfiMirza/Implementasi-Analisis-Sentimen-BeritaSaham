<?php

namespace App\Services\MarketData;

use App\Models\IdxDailySummary;
use App\Models\KseiOwnership;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

/**
 * Turns the raw idx_daily_summaries table into the four descriptive alert lists shown on the
 * Market Alerts page: unusual volume, price gap / big move, net foreign flow, and (from KSEI)
 * month-over-month ownership shift.
 *
 * These are observations, not trading signals -- nothing here is validated OOS or fed into the
 * prediction/DSS pipeline (see the repo rule about not building signals on unvalidated metrics).
 */
class IdxMarketSummaryService
{
    public function latestTradeDate(): ?string
    {
        $value = IdxDailySummary::max('trade_date');

        return $value ? Carbon::parse($value)->toDateString() : null;
    }

    /**
     * Full payload for the page / JSON endpoint. Cached per trade date.
     *
     * @return array<string, mixed>
     */
    public function summary(bool $fresh = false): array
    {
        $date = $this->latestTradeDate();
        if ($date === null) {
            return $this->emptyPayload();
        }

        $key = "market_alerts:summary:{$date}";
        if ($fresh) {
            Cache::forget($key);
        }

        $minutes = (int) config('market_alerts.cache_minutes', 15);

        return Cache::remember($key, now()->addMinutes($minutes), function () use ($date): array {
            $volume = $this->volumeAlerts($date);
            $gap = $this->gapAlerts($date);
            $foreign = $this->foreignFlowAlerts($date);
            $ownership = $this->ownershipAlerts();

            return [
                'trade_date' => $date,
                'generated_at' => now()->toIso8601String(),
                'universe' => IdxDailySummary::whereDate('trade_date', $date)->count(),
                'source' => IdxDailySummary::whereDate('trade_date', $date)->value('source') ?? 'idx_scrape',
                'counts' => [
                    'volume' => count($volume),
                    'gap' => count($gap),
                    'foreign' => count($foreign),
                    'ownership' => count($ownership),
                ],
                'volume' => $volume,
                'gap' => $gap,
                'foreign' => $foreign,
                'ownership' => $ownership,
            ];
        });
    }

    /**
     * Volume today vs the average over the previous N trading days.
     *
     * @return array<int, array<string, mixed>>
     */
    public function volumeAlerts(string $date): array
    {
        $lookback = (int) config('market_alerts.volume_lookback', 20);
        $cfg = config('market_alerts.volume');

        $priorDates = IdxDailySummary::query()
            ->whereDate('trade_date', '<', $date)
            ->distinct()
            ->orderByDesc('trade_date')
            ->limit($lookback)
            ->pluck('trade_date')
            ->map(fn ($d) => Carbon::parse($d)->toDateString())
            ->unique()
            ->values()
            ->all();

        if (count($priorDates) < 5) {
            return []; // not enough history to say anything is "unusual"
        }

        $rows = DB::table('idx_daily_summaries as t')
            ->join('idx_daily_summaries as p', function ($join) use ($priorDates) {
                $join->on('p.stock_code', '=', 't.stock_code')
                    ->whereIn(DB::raw('date(p.trade_date)'), $priorDates);
            })
            ->whereRaw('date(t.trade_date) = ?', [$date])
            ->groupBy('t.stock_code', 't.stock_name', 't.close', 't.volume', 't.value', 't.pct_change', 't.frequency')
            ->select([
                't.stock_code', 't.stock_name', 't.close', 't.value', 't.pct_change', 't.frequency',
                't.volume as volume',
                DB::raw('AVG(p.volume) as avg_volume'),
            ])
            ->havingRaw('AVG(p.volume) > 0')
            // Thresholds are interpolated (trusted config, not user input) -- binding them as
            // PHP floats trips SQLite's numeric-vs-text affinity rule and silently drops rows.
            ->havingRaw('t.volume >= '.(float) $cfg['min_ratio'].' * AVG(p.volume)')
            ->havingRaw('t.value >= '.(float) $cfg['min_value_rp'])
            ->orderByRaw('t.volume * 1.0 / AVG(p.volume) DESC')
            ->limit((int) $cfg['limit'])
            ->get();

        return $rows->map(function ($r): array {
            $ratio = $r->avg_volume > 0 ? $r->volume / $r->avg_volume : null;

            return [
                'stock_code' => $r->stock_code,
                'stock_name' => $r->stock_name,
                'close' => (float) $r->close,
                'pct_change' => $r->pct_change !== null ? (float) $r->pct_change : null,
                'volume' => (int) $r->volume,
                'avg_volume' => (int) round($r->avg_volume),
                'volume_ratio' => $ratio !== null ? round($ratio, 2) : null,
                'value' => (float) $r->value,
                'frequency' => (int) $r->frequency,
                'direction' => $this->direction($r->pct_change),
            ];
        })->all();
    }

    /**
     * Opening gap vs previous close, or a large close-to-close move.
     *
     * @return array<int, array<string, mixed>>
     */
    public function gapAlerts(string $date): array
    {
        $cfg = config('market_alerts.gap');

        return IdxDailySummary::query()
            ->whereDate('trade_date', $date)
            ->where('previous', '>', 0)
            ->where('value', '>=', (float) $cfg['min_value_rp'])
            ->where(function ($q) use ($cfg) {
                // A 0 open means no opening auction -- treat as "no gap", only the move branch applies.
                $q->where(function ($g) use ($cfg) {
                    $g->where('open', '>', 0)
                        ->whereRaw('ABS(`open` - previous) * 100.0 / previous >= '.(float) $cfg['min_gap_pct']);
                })->orWhereRaw('ABS(pct_change) >= '.(float) $cfg['min_move_pct']);
            })
            ->orderByRaw('ABS(pct_change) DESC')
            ->limit((int) $cfg['limit'])
            ->get()
            ->map(function (IdxDailySummary $r): array {
                $gapPct = ($r->previous > 0 && $r->open !== null && $r->open > 0)
                    ? round(($r->open - $r->previous) / $r->previous * 100, 2)
                    : null;

                return [
                    'stock_code' => $r->stock_code,
                    'stock_name' => $r->stock_name,
                    'previous' => $r->previous,
                    'open' => $r->open,
                    'close' => $r->close,
                    'gap_pct' => $gapPct,
                    'pct_change' => $r->pct_change,
                    'volume' => $r->volume,
                    'value' => $r->value,
                    'direction' => $this->direction($r->pct_change),
                ];
            })->all();
    }

    /**
     * Biggest net foreign positions of the day by absolute rupiah (approx = net shares * close).
     *
     * Foreign flow at the market level is an absolute-rupiah story -- a large % of a thin stock's
     * turnover moves nothing that matters. `net_ratio` is still returned as table context, but it
     * is deliberately NOT a qualifying condition (that "OR ratio" branch surfaced ~150 rows/day,
     * mostly illiquid names).
     *
     * @return array<int, array<string, mixed>>
     */
    public function foreignFlowAlerts(string $date): array
    {
        $cfg = config('market_alerts.foreign');

        return IdxDailySummary::query()
            ->whereDate('trade_date', $date)
            ->whereRaw('ABS(foreign_net_value) >= '.(float) $cfg['min_net_value_rp'])
            ->orderByRaw('ABS(foreign_net_value) DESC')
            ->limit((int) $cfg['limit'])
            ->get()
            ->map(function (IdxDailySummary $r): array {
                return [
                    'stock_code' => $r->stock_code,
                    'stock_name' => $r->stock_name,
                    'close' => $r->close,
                    'pct_change' => $r->pct_change,
                    'foreign_net_shares' => $r->foreign_net,
                    'foreign_net_value' => $r->foreign_net_value,
                    'value' => $r->value,
                    'net_ratio' => $r->value > 0 ? round($r->foreign_net_value / $r->value * 100, 1) : null,
                    'direction' => $r->foreign_net > 0 ? 'inflow' : ($r->foreign_net < 0 ? 'outflow' : 'flat'),
                ];
            })->all();
    }

    /**
     * Per-day net foreign flow for one stock over the last N trading days, plus a small
     * consistency summary -- this is what answers "which days did foreign money actually come
     * in", instead of the one-day snapshot the alert list shows.
     *
     * @return array<string, mixed>
     */
    public function foreignFlowHistory(string $code, int $days = 20): array
    {
        $code = strtoupper(trim($code));
        $days = max(5, min(60, $days));

        $rows = IdxDailySummary::query()
            ->where('stock_code', $code)
            ->orderByDesc('trade_date')
            ->limit($days)
            ->get([
                'trade_date', 'close', 'pct_change', 'value',
                'foreign_net', 'foreign_net_value',
            ])
            ->map(fn (IdxDailySummary $r): array => [
                'date' => Carbon::parse($r->trade_date)->toDateString(),
                'close' => $r->close,
                'pct_change' => $r->pct_change,
                'net_shares' => $r->foreign_net,
                'net_value' => $r->foreign_net_value,
                'net_ratio' => $r->value > 0 ? round($r->foreign_net_value / $r->value * 100, 1) : null,
            ])
            // oldest -> newest for reading left to right
            ->sortBy('date')
            ->values();

        if ($rows->isEmpty()) {
            return ['stock_code' => $code, 'days' => [], 'summary' => null];
        }

        $buyDays = $rows->where('net_value', '>', 0)->count();
        $sellDays = $rows->where('net_value', '<', 0)->count();
        $netTotal = round((float) $rows->sum('net_value'), 2);

        // Current run length of same-sign days, counting back from the latest.
        $streak = 0;
        $streakDir = null;
        foreach ($rows->reverse()->values() as $r) {
            $dir = $r['net_value'] > 0 ? 'buy' : ($r['net_value'] < 0 ? 'sell' : 'flat');
            if ($dir === 'flat') {
                break;
            }
            if ($streakDir === null) {
                $streakDir = $dir;
            }
            if ($dir !== $streakDir) {
                break;
            }
            $streak++;
        }

        return [
            'stock_code' => $code,
            'days' => $rows->all(),
            'summary' => [
                'window' => $rows->count(),
                'buy_days' => $buyDays,
                'sell_days' => $sellDays,
                'net_total_value' => $netTotal,
                'streak' => $streak,
                'streak_dir' => $streak > 0 ? $streakDir : null,
            ],
        ];
    }

    /**
     * Month-over-month foreign ownership shift from the latest KSEI snapshot (may be empty
     * until `ksei:fetch-ownership` has run).
     *
     * @return array<int, array<string, mixed>>
     */
    public function ownershipAlerts(): array
    {
        $snapshot = KseiOwnership::max('snapshot_date');
        if ($snapshot === null) {
            return [];
        }
        // Normalise -- SQLite stores a `date` cast as "Y-m-d H:i:s", which whereDate() would miss.
        $snapshot = Carbon::parse($snapshot)->toDateString();

        $cfg = config('market_alerts.ownership');

        return KseiOwnership::query()
            ->whereDate('snapshot_date', $snapshot)
            ->whereNotNull('foreign_pct_delta')
            ->whereRaw('ABS(foreign_pct_delta) >= '.(float) $cfg['min_foreign_pct_delta'])
            ->orderByRaw('ABS(foreign_pct_delta) DESC')
            ->limit((int) $cfg['limit'])
            ->get()
            ->map(fn (KseiOwnership $r): array => [
                'stock_code' => $r->stock_code,
                'stock_name' => $r->stock_name,
                'snapshot_date' => Carbon::parse($r->snapshot_date)->toDateString(),
                'foreign_pct' => $r->foreign_pct,
                'local_pct' => $r->local_pct,
                'foreign_pct_delta' => $r->foreign_pct_delta,
                'direction' => $r->foreign_pct_delta > 0 ? 'accumulation' : 'distribution',
                'source' => $r->source,
            ])->all();
    }

    private function direction(mixed $pctChange): string
    {
        $pct = (float) ($pctChange ?? 0);

        return $pct > 0 ? 'up' : ($pct < 0 ? 'down' : 'flat');
    }

    /** @return array<string, mixed> */
    private function emptyPayload(): array
    {
        return [
            'trade_date' => null,
            'generated_at' => now()->toIso8601String(),
            'universe' => 0,
            'source' => null,
            'counts' => ['volume' => 0, 'gap' => 0, 'foreign' => 0, 'ownership' => 0],
            'volume' => [],
            'gap' => [],
            'foreign' => [],
            'ownership' => [],
        ];
    }
}
