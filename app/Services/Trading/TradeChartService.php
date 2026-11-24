<?php

namespace App\Services\Trading;

use App\Models\Stock;
use App\Models\StockPrice;
use App\Models\Trade;
use App\Services\News\NewsEventClassifierService;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class TradeChartService
{
    private NewsEventClassifierService $newsClassifier;

    public function __construct(?NewsEventClassifierService $newsClassifier = null)
    {
        $this->newsClassifier = $newsClassifier ?? app(NewsEventClassifierService::class);
    }
    /**
     * Build complete OHLCV, technical indicators, strategy levels, and markers
     * for TradingView Lightweight Charts on /trades/{trade}.
     *
     * @return array<string, mixed>
     */
    public function buildChartPayload(Trade $trade, string $timeframe = '1d'): array
    {
        $tf = in_array($timeframe, ['15m', '1d'], true) ? $timeframe : '1d';
        $stock = $trade->stock ?? Stock::where('code', strtoupper((string) $trade->ticker))->first();
        $ticker = strtoupper((string) ($stock?->code ?? $trade->ticker));

        $bars = $tf === '15m'
            ? $this->loadIntradayBars($ticker, $trade)
            : $this->loadDailyBars($stock, $trade);

        $fallbackUsed = false;
        if ($tf === '15m' && count($bars) < 5) {
            // Fallback ke daily jika data 15m tidak tersedia untuk rentang tanggal trade lama
            $bars = $this->loadDailyBars($stock, $trade);
            $tf = '1d';
            $fallbackUsed = true;
        }

        $indicators = $this->computeIndicators($bars);
        $levels = $this->computeStrategyLevels($trade, $bars, $tf);

        $untilDate = ($trade->status === 'closed' && ($trade->closed_at || $trade->exit_date))
            ? Carbon::parse($trade->closed_at ?? $trade->exit_date)->timezone('Asia/Jakarta')->addDays(7)->toDateString()
            : null;
        $newsSummary = $this->newsClassifier->summarizeForTicker($ticker, 30, $untilDate);
        $markers = $this->buildMarkers($trade, $bars, $levels, $tf, $newsSummary['events'] ?? []);

        $lastBar = count($bars) > 0 ? $bars[count($bars) - 1] : null;
        $hasIntraday = $this->hasIntradayData($ticker, $trade);

        return [
            'trade' => [
                'id' => $trade->id,
                'ticker' => $ticker,
                'company_name' => $stock?->company_name ?? $ticker,
                'strategy_label' => $trade->strategy_label ?? 'gabungan',
                'signal_quality' => $trade->signal_quality,
                'status' => $trade->status,
                'result' => $trade->result,
                'entry_price' => (float) $trade->entry_price,
                'exit_price' => $trade->exit_price !== null ? (float) $trade->exit_price : null,
                'lot_size' => (int) $trade->lot_size,
                'lots' => (int) round(((int) $trade->lot_size) / 100),
                'position_value' => (float) $trade->position_value,
                'entry_date' => $trade->entry_date?->timezone('Asia/Jakarta')->format('Y-m-d'),
                'exit_date' => $trade->exit_date?->timezone('Asia/Jakarta')->format('Y-m-d'),
                'closed_at' => $trade->closed_at?->timezone('Asia/Jakarta')->format('Y-m-d H:i'),
                'pnl_percent' => $trade->pnl_percent !== null ? (float) $trade->pnl_percent : null,
                'pnl_total' => $trade->pnl_total !== null ? (float) $trade->pnl_total : null,
            ],
            'timeframe' => $tf,
            'fallback_to_daily' => $fallbackUsed,
            'has_intraday' => $hasIntraday,
            'candles' => array_map(fn (array $b) => [
                'time' => $b['time'],
                'open' => $b['open'],
                'high' => $b['high'],
                'low' => $b['low'],
                'close' => $b['close'],
            ], $bars),
            'volume' => $indicators['volume'],
            'ma20' => $indicators['ma20'],
            'high20' => $indicators['high20'],
            'bb_upper' => $indicators['bb_upper'],
            'bb_lower' => $indicators['bb_lower'],
            'rsi14' => $indicators['rsi14'],
            'macd' => $indicators['macd'],
            'levels' => $levels,
            'markers' => $markers,
            'news_summary' => $newsSummary,
            'last_bar' => $lastBar,
        ];
    }

    /**
     * @return list<array{time: string, raw_date: string, open: float, high: float, low: float, close: float, volume: float}>
     */
    private function loadDailyBars(?Stock $stock, Trade $trade): array
    {
        if (! $stock) {
            return [];
        }

        $entryDate = $trade->entry_date ? Carbon::parse($trade->entry_date)->timezone('Asia/Jakarta') : now('Asia/Jakarta');
        $startDate = $entryDate->copy()->subDays(120)->toDateString();

        $query = StockPrice::query()
            ->where('stock_id', $stock->id)
            ->whereDate('price_date', '>=', $startDate)
            ->whereNotNull('close')
            ->orderBy('price_date');

        if ($trade->status === 'closed' && ($trade->exit_date || $trade->closed_at)) {
            $exitRef = $trade->closed_at ?? $trade->exit_date;
            $endDate = Carbon::parse($exitRef)->timezone('Asia/Jakarta')->addDays(45)->toDateString();
            $query->whereDate('price_date', '<=', $endDate);
        }

        $rows = $query->get();
        if (method_exists(StockPrice::class, 'canonicalize')) {
            $rows = StockPrice::canonicalize($rows);
        }

        $byDate = [];
        foreach ($rows as $row) {
            $dateStr = Carbon::parse($row->price_date)->format('Y-m-d');
            $open = (float) ($row->open ?: $row->close);
            $high = (float) ($row->high ?: max($open, (float) $row->close));
            $low = (float) ($row->low ?: min($open, (float) $row->close));
            $close = (float) $row->close;
            if ($close <= 0) {
                continue;
            }
            $byDate[$dateStr] = [
                'time' => $dateStr,
                'raw_date' => $dateStr,
                'open' => $open,
                'high' => max($high, $open, $close),
                'low' => min($low, $open, $close),
                'close' => $close,
                'volume' => (float) ($row->volume ?? 0),
            ];
        }

        ksort($byDate);

        return array_values($byDate);
    }

    /**
     * @return list<array{time: int, raw_date: string, raw_time: string, open: float, high: float, low: float, close: float, volume: float}>
     */
    private function loadIntradayBars(string $ticker, Trade $trade): array
    {
        if (! Schema::hasTable('intraday_prices')) {
            return [];
        }

        $entryDate = $trade->entry_date ? Carbon::parse($trade->entry_date)->timezone('Asia/Jakarta') : now('Asia/Jakarta');
        $startAt = $entryDate->copy()->subDays(7)->startOfDay()->format('Y-m-d H:i:s');

        $query = DB::table('intraday_prices')
            ->where('stock_code', $ticker)
            ->where('interval', '15m')
            ->where('bar_time', '>=', $startAt)
            ->orderBy('bar_time');

        if ($trade->status === 'closed' && ($trade->closed_at || $trade->exit_date)) {
            $exitRef = $trade->closed_at ?? $trade->exit_date;
            $endAt = Carbon::parse($exitRef)->timezone('Asia/Jakarta')->addDays(5)->endOfDay()->format('Y-m-d H:i:s');
            $query->where('bar_time', '<=', $endAt);
        }

        $rows = $query->limit(320)->get();
        $bars = [];
        $seen = [];

        foreach ($rows as $row) {
            $close = (float) $row->close;
            if ($close <= 0) {
                continue;
            }
            // Treat stored WIB wall-clock string as UTC epoch so Lightweight Charts shows exact WIB hours
            $ts = Carbon::createFromFormat('Y-m-d H:i:s', (string) $row->bar_time, 'UTC')->timestamp;
            if (isset($seen[$ts])) {
                continue;
            }
            $seen[$ts] = true;

            $open = (float) ($row->open ?: $close);
            $high = (float) ($row->high ?: max($open, $close));
            $low = (float) ($row->low ?: min($open, $close));

            $bars[] = [
                'time' => $ts,
                'raw_date' => substr((string) $row->bar_time, 0, 10),
                'raw_time' => (string) $row->bar_time,
                'open' => $open,
                'high' => max($high, $open, $close),
                'low' => min($low, $open, $close),
                'close' => $close,
                'volume' => (float) ($row->volume ?? 0),
            ];
        }

        return $bars;
    }

    private function hasIntradayData(string $ticker, Trade $trade): bool
    {
        if (! Schema::hasTable('intraday_prices')) {
            return false;
        }

        $entryDate = $trade->entry_date ? Carbon::parse($trade->entry_date)->timezone('Asia/Jakarta') : now('Asia/Jakarta');
        $startAt = $entryDate->copy()->subDays(7)->startOfDay()->format('Y-m-d H:i:s');

        $query = DB::table('intraday_prices')
            ->where('stock_code', $ticker)
            ->where('interval', '15m')
            ->where('bar_time', '>=', $startAt);

        if ($trade->status === 'closed' && ($trade->closed_at || $trade->exit_date)) {
            $exitRef = $trade->closed_at ?? $trade->exit_date;
            $endAt = Carbon::parse($exitRef)->timezone('Asia/Jakarta')->addDays(5)->endOfDay()->format('Y-m-d H:i:s');
            $query->where('bar_time', '<=', $endAt);
        }

        return $query->limit(5)->count() >= 5;
    }

    /**
     * @param  list<array<string, mixed>>  $bars
     * @return array<string, mixed>
     */
    private function computeIndicators(array $bars): array
    {
        $n = count($bars);
        $closes = array_column($bars, 'close');
        $highs = array_column($bars, 'high');
        $volumes = array_column($bars, 'volume');

        $ma20 = [];
        $high20 = [];
        $bbUpper = [];
        $bbLower = [];
        $volumeSeries = [];

        for ($i = 0; $i < $n; $i++) {
            $time = $bars[$i]['time'];

            // Volume + spike detection (>= 1.5x 20-bar avg volume)
            $volStart = max(0, $i - 20);
            $volWindow = array_slice($volumes, $volStart, $i - $volStart);
            $volAvg = count($volWindow) > 0 ? array_sum($volWindow) / count($volWindow) : 0.0;
            $isSpike = $volAvg > 0 && $volumes[$i] >= ($volAvg * 1.5);
            $isUp = $bars[$i]['close'] >= $bars[$i]['open'];

            $volColor = $isSpike
                ? 'rgba(251, 191, 36, 0.78)' // amber/gold for Volume Spike
                : ($isUp ? 'rgba(16, 185, 129, 0.38)' : 'rgba(244, 63, 94, 0.38)');

            $volumeSeries[] = [
                'time' => $time,
                'value' => $volumes[$i],
                'color' => $volColor,
                'is_spike' => $isSpike,
            ];

            if ($i >= 19) {
                $slice = array_slice($closes, $i - 19, 20);
                $mean = array_sum($slice) / 20.0;
                $variance = 0.0;
                foreach ($slice as $v) {
                    $variance += ($v - $mean) ** 2;
                }
                $std = sqrt($variance / 20.0);

                $ma20[] = ['time' => $time, 'value' => round($mean, 2)];
                $bbUpper[] = ['time' => $time, 'value' => round($mean + 2 * $std, 2)];
                $bbLower[] = ['time' => $time, 'value' => round($mean - 2 * $std, 2)];

                $highSlice = array_slice($highs, $i - 19, 20);
                $high20[] = ['time' => $time, 'value' => round(max($highSlice), 2)];
            }
        }

        // RSI(14) Wilder EWM
        $rsi14 = [];
        $period = 14;
        $alpha = 1.0 / $period;
        $avgGain = null;
        $avgLoss = null;
        for ($i = 1; $i < $n; $i++) {
            $delta = $closes[$i] - $closes[$i - 1];
            $gain = max($delta, 0.0);
            $loss = max(-$delta, 0.0);

            if ($avgGain === null) {
                $avgGain = $gain;
                $avgLoss = $loss;
            } else {
                $avgGain = (1.0 - $alpha) * $avgGain + $alpha * $gain;
                $avgLoss = (1.0 - $alpha) * $avgLoss + $alpha * $loss;
            }

            if ($i >= $period) {
                $rsiVal = $avgLoss == 0.0 ? 100.0 : 100.0 - (100.0 / (1.0 + ($avgGain / $avgLoss)));
                $rsi14[] = ['time' => $bars[$i]['time'], 'value' => round($rsiVal, 2)];
            }
        }

        // MACD (12, 26, 9)
        $ema12 = $this->computeEma($closes, 12);
        $ema26 = $this->computeEma($closes, 26);
        $macdRaw = [];
        $macdIndices = [];
        for ($i = 0; $i < $n; $i++) {
            if ($ema12[$i] !== null && $ema26[$i] !== null) {
                $macdRaw[] = $ema12[$i] - $ema26[$i];
                $macdIndices[] = $i;
            }
        }
        $signalRaw = $this->computeEma($macdRaw, 9);

        $macdLine = [];
        $signalLine = [];
        $histogram = [];
        foreach ($macdRaw as $k => $mVal) {
            $barIdx = $macdIndices[$k];
            $time = $bars[$barIdx]['time'];
            $macdLine[] = ['time' => $time, 'value' => round($mVal, 3)];
            if ($signalRaw[$k] !== null) {
                $sVal = $signalRaw[$k];
                $hVal = $mVal - $sVal;
                $signalLine[] = ['time' => $time, 'value' => round($sVal, 3)];
                $histogram[] = [
                    'time' => $time,
                    'value' => round($hVal, 3),
                    'color' => $hVal >= 0 ? 'rgba(16, 185, 129, 0.65)' : 'rgba(244, 63, 94, 0.65)',
                ];
            }
        }

        return [
            'volume' => $volumeSeries,
            'ma20' => $ma20,
            'high20' => $high20,
            'bb_upper' => $bbUpper,
            'bb_lower' => $bbLower,
            'rsi14' => $rsi14,
            'macd' => [
                'macd' => $macdLine,
                'signal' => $signalLine,
                'histogram' => $histogram,
            ],
        ];
    }

    /**
     * @param  list<float>  $values
     * @return list<?float>
     */
    private function computeEma(array $values, int $period): array
    {
        $n = count($values);
        $result = array_fill(0, $n, null);
        if ($n < $period) {
            return $result;
        }

        $k = 2.0 / ($period + 1);
        $sma = array_sum(array_slice($values, 0, $period)) / $period;
        $result[$period - 1] = $sma;
        $prev = $sma;

        for ($i = $period; $i < $n; $i++) {
            $prev = ($values[$i] - $prev) * $k + $prev;
            $result[$i] = $prev;
        }

        return $result;
    }

    /**
     * Compute Entry, Hard SL, TP1/TP2, Peak/MFE, and Dynamic Trailing Stop
     * strictly following GEMINI.md 3-Layer Exit Protocol.
     *
     * @param  list<array<string, mixed>>  $bars
     * @return array<string, mixed>
     */
    private function computeStrategyLevels(Trade $trade, array $bars, string $tf): array
    {
        $entry = (float) $trade->entry_price;
        $strategy = strtolower((string) ($trade->strategy_label ?? 'gabungan'));

        $defaultSlPct = in_array($strategy, ['bottom_to_top', 'bsjp'], true) ? 3.0 : 3.5;
        $stopLoss = (float) $trade->stop_loss > 0
            ? (float) $trade->stop_loss
            : round($entry * (1 - $defaultSlPct / 100), 2);

        $target1 = (float) $trade->target_1 > 0 ? (float) $trade->target_1 : round($entry * 1.05, 2);
        $target2 = $trade->target_2 !== null && (float) $trade->target_2 > 0 ? (float) $trade->target_2 : null;

        $pullbackPct = $strategy === 'bottom_to_top' ? 2.5 : 2.0;
        $activationGainPct = $strategy === 'bottom_to_top' ? 3.0 : 0.0;

        $entryDateStr = $trade->entry_date ? Carbon::parse($trade->entry_date)->timezone('Asia/Jakarta')->format('Y-m-d') : null;
        $exitDateStr = $trade->status === 'closed'
            ? ($trade->closed_at
                ? Carbon::parse($trade->closed_at)->timezone('Asia/Jakarta')->format('Y-m-d')
                : ($trade->exit_date ? Carbon::parse($trade->exit_date)->timezone('Asia/Jakarta')->format('Y-m-d') : null))
            : null;

        $peakPrice = $entry;
        $peakTime = null;

        foreach ($bars as $bar) {
            $barDate = (string) $bar['raw_date'];
            if ($entryDateStr !== null && $barDate <= $entryDateStr) {
                continue;
            }
            if ($exitDateStr !== null && $barDate > $exitDateStr) {
                break;
            }
            if ($bar['high'] > $peakPrice) {
                $peakPrice = (float) $bar['high'];
                $peakTime = $bar['time'];
            }
        }

        $mfePct = $entry > 0 ? round((($peakPrice - $entry) / $entry) * 100, 2) : 0.0;
        $trailingActive = $peakPrice > $entry && $mfePct >= $activationGainPct;
        $trailingStopPrice = $trailingActive
            ? round($peakPrice * (1 - $pullbackPct / 100), 2)
            : null;

        return [
            'entry' => $entry,
            'stop_loss' => $stopLoss,
            'sl_pct' => $entry > 0 ? round((($stopLoss - $entry) / $entry) * 100, 2) : -$defaultSlPct,
            'target_1' => $target1,
            'tp1_pct' => $entry > 0 ? round((($target1 - $entry) / $entry) * 100, 2) : 0.0,
            'target_2' => $target2,
            'tp2_pct' => ($target2 !== null && $entry > 0) ? round((($target2 - $entry) / $entry) * 100, 2) : null,
            'peak_price' => $peakPrice,
            'peak_time' => $peakTime,
            'mfe_pct' => $mfePct,
            'trailing_pullback_pct' => $pullbackPct,
            'trailing_activation_pct' => $activationGainPct,
            'trailing_active' => $trailingActive,
            'trailing_stop' => $trailingStopPrice,
        ];
    }

    /**
     * Build Lightweight Charts markers for BUY, PEAK, EXIT, and dated News Catalyst/Risk events.
     *
     * @param  list<array<string, mixed>>  $bars
     * @param  array<string, mixed>  $levels
     * @param  list<array<string, mixed>>  $newsEvents
     * @return list<array<string, mixed>>
     */
    private function buildMarkers(Trade $trade, array $bars, array $levels, string $tf, array $newsEvents = []): array
    {
        if (count($bars) === 0) {
            return [];
        }

        $markers = [];
        $entryDateStr = $trade->entry_date ? Carbon::parse($trade->entry_date)->timezone('Asia/Jakarta')->format('Y-m-d') : null;
        $entryBar = $this->findClosestBar($bars, $entryDateStr, true);

        if ($entryBar !== null) {
            $grade = $trade->signal_quality ? ' ' . strtoupper((string) $trade->signal_quality) : '';
            $markers[] = [
                'time' => $entryBar['time'],
                'position' => 'belowBar',
                'color' => '#38bdf8',
                'shape' => 'arrowUp',
                'text' => 'BUY' . $grade . ' @ ' . number_format((float) $trade->entry_price, 0, ',', '.'),
            ];
        }

        if ($levels['peak_time'] !== null && $levels['peak_price'] > (float) $trade->entry_price) {
            $markers[] = [
                'time' => $levels['peak_time'],
                'position' => 'aboveBar',
                'color' => '#fbbf24',
                'shape' => 'circle',
                'text' => 'PEAK +' . number_format((float) $levels['mfe_pct'], 1) . '%',
            ];
        }

        if ($trade->status === 'closed' && $trade->exit_price !== null) {
            $exitRef = $trade->closed_at ?? $trade->exit_date;
            $exitDateStr = $exitRef ? Carbon::parse($exitRef)->timezone('Asia/Jakarta')->format('Y-m-d') : null;
            $exitBar = $this->findClosestBar($bars, $exitDateStr, false);

            if ($exitBar !== null) {
                $pnlPct = (float) ($trade->pnl_percent ?? 0);
                $isWin = $pnlPct >= 0;
                $resTag = match ($trade->result) {
                    'stop_loss' => 'SL',
                    'trailing_stop', 'trailing_stop_1pct', 'trailing_stop_1_5pct' => 'TS',
                    'hit_target_1' => 'TP1',
                    'hit_target_2' => 'TP2',
                    'time_target' => 'TIME',
                    default => 'EXIT',
                };
                $sign = $pnlPct >= 0 ? '+' : '';
                $markers[] = [
                    'time' => $exitBar['time'],
                    'position' => 'aboveBar',
                    'color' => $isWin ? '#10b981' : '#f43f5e',
                    'shape' => 'arrowDown',
                    'text' => "{$resTag} {$sign}" . number_format($pnlPct, 2) . '%',
                ];
            }
        }

        // News Catalyst / Hard Risk / Suspension markers (max 4 most important dated events within chart range)
        $minDate = $bars[0]['raw_date'] ?? null;
        $maxDate = $bars[count($bars) - 1]['raw_date'] ?? null;
        $addedNewsDates = [];
        foreach ($newsEvents as $ev) {
            if (count($addedNewsDates) >= 4) {
                break;
            }
            $tag = (string) ($ev['tag'] ?? '');
            $evDate = (string) ($ev['date'] ?? '');
            if (! in_array($tag, ['SUSPENSION_ALERT', 'HARD_RISK', 'CATALYST'], true) || $evDate === '') {
                continue;
            }
            if (($minDate && $evDate < $minDate) || ($maxDate && $evDate > $maxDate) || isset($addedNewsDates[$evDate])) {
                continue;
            }
            $newsBar = $this->findClosestBar($bars, $evDate, true);
            if ($newsBar !== null) {
                $addedNewsDates[$evDate] = true;
                $markers[] = [
                    'time' => $newsBar['time'],
                    'position' => $tag === 'CATALYST' ? 'belowBar' : 'aboveBar',
                    'color' => $tag === 'CATALYST' ? '#10b981' : '#f43f5e',
                    'shape' => 'square',
                    'text' => $tag === 'CATALYST' ? '📰 CATALYST' : ($tag === 'SUSPENSION_ALERT' ? '⛔ UMA/SUSP' : '📰 RISK'),
                ];
            }
        }

        // Lightweight Charts requires markers strictly sorted by ascending time
        usort($markers, fn (array $a, array $b) => $a['time'] <=> $b['time']);

        return $markers;
    }

    /**
     * @param  list<array<string, mixed>>  $bars
     * @return ?array<string, mixed>
     */
    private function findClosestBar(array $bars, ?string $targetDate, bool $preferLastOfDay): ?array
    {
        if ($targetDate === null) {
            return null;
        }

        $exactMatches = array_values(array_filter($bars, fn (array $b) => $b['raw_date'] === $targetDate));
        if (count($exactMatches) > 0) {
            return $preferLastOfDay ? $exactMatches[count($exactMatches) - 1] : $exactMatches[0];
        }

        // Nearest bar on or after targetDate
        foreach ($bars as $b) {
            if ($b['raw_date'] >= $targetDate) {
                return $b;
            }
        }

        return $bars[count($bars) - 1] ?? null;
    }
}

