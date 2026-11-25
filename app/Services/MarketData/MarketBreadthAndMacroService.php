<?php

namespace App\Services\MarketData;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Schema;
use Throwable;

/**
 * Fase FG-2: Market Breadth & Overnight Macro Risk Gate.
 *
 * Computes internal IDX breadth (% gainers & near-ARB count) from official `idx_daily_summaries`
 * and evaluates overnight macro stress (USD/IDR, Nasdaq, Gold, Brent) to protect BSJP &
 * momentum entries from macro gap-down regimes.
 */
class MarketBreadthAndMacroService
{
    private const MACRO_SYMBOLS = [
        'usdidr' => 'IDR=X',
        'nasdaq' => '^IXIC',
        'sp500' => '^GSPC',
        'gold' => 'GC=F',
        'brent' => 'BZ=F',
    ];

    /**
     * Build combined live breadth + macro risk gate payload.
     *
     * @return array<string, mixed>
     */
    public function buildGate(?array $macroOverride = null): array
    {
        $breadth = $this->computeLatestBreadth();
        $macro = $macroOverride ?? $this->fetchMacroSnapshot();

        return $this->evaluateRiskGate($breadth, $macro);
    }

    /**
     * Compute latest official IDX market breadth from `idx_daily_summaries`.
     *
     * @return array<string, mixed>
     */
    public function computeLatestBreadth(): array
    {
        if (! Schema::hasTable('idx_daily_summaries')) {
            return [
                'trade_date' => null,
                'total_active' => 0,
                'gainers' => 0,
                'losers' => 0,
                'flat' => 0,
                'gainers_pct' => null,
                'near_arb_count' => 0,
                'total_foreign_net_rp' => 0.0,
            ];
        }

        $latestDate = DB::table('idx_daily_summaries')
            ->where('source', 'idx_scrape')
            ->max('trade_date')
            ?? DB::table('idx_daily_summaries')->max('trade_date');

        if (! $latestDate) {
            return [
                'trade_date' => null,
                'total_active' => 0,
                'gainers' => 0,
                'losers' => 0,
                'flat' => 0,
                'gainers_pct' => null,
                'near_arb_count' => 0,
                'total_foreign_net_rp' => 0.0,
            ];
        }

        $rows = DB::table('idx_daily_summaries')
            ->whereDate('trade_date', $latestDate)
            ->where('volume', '>', 0)
            ->get(['pct_change', 'foreign_net_value']);

        $total = $rows->count();
        $gainers = $rows->filter(fn ($r) => (float) $r->pct_change > 0)->count();
        $losers = $rows->filter(fn ($r) => (float) $r->pct_change < 0)->count();
        $flat = $total - $gainers - $losers;
        $nearArb = $rows->filter(fn ($r) => (float) $r->pct_change <= -6.5)->count();
        $foreignNet = (float) $rows->sum('foreign_net_value');

        return [
            'trade_date' => (string) $latestDate,
            'total_active' => $total,
            'gainers' => $gainers,
            'losers' => $losers,
            'flat' => $flat,
            'gainers_pct' => $total > 0 ? round(($gainers / $total) * 100.0, 1) : null,
            'near_arb_count' => $nearArb,
            'total_foreign_net_rp' => round($foreignNet, 0),
        ];
    }

    /**
     * Evaluate combined breadth + overnight macro snapshot into a deterministic gate verdict.
     *
     * @param  array<string, mixed>  $breadth
     * @param  array<string, array{close: float, chg_pct: float}>  $macro
     * @return array<string, mixed>
     */
    public function evaluateRiskGate(array $breadth, array $macro): array
    {
        $flags = [];
        $riskScore = 0;

        $gainersPct = $breadth['gainers_pct'] ?? null;
        if ($gainersPct !== null) {
            if ($gainersPct < 25.0) {
                $riskScore += 3;
                $flags[] = sprintf('Breadth ekstrem lemah (%.1f%% gainers < 25%%)', $gainersPct);
            } elseif ($gainersPct < 40.0) {
                $riskScore += 1;
                $flags[] = sprintf('Breadth lemah (%.1f%% gainers < 40%%)', $gainersPct);
            }
        }

        if (($breadth['near_arb_count'] ?? 0) >= 15) {
            $riskScore += 2;
            $flags[] = sprintf('%d saham mendekati/terkunci ARB', (int) $breadth['near_arb_count']);
        }

        $nasdaqChg = $macro['nasdaq']['chg_pct'] ?? null;
        if ($nasdaqChg !== null && $nasdaqChg <= -1.5) {
            $riskScore += 2;
            $flags[] = sprintf('Nasdaq overnight anjlok (%+.2f%%)', $nasdaqChg);
        }

        $sp500Chg = $macro['sp500']['chg_pct'] ?? null;
        if ($sp500Chg !== null && $sp500Chg <= -1.0) {
            $riskScore += 2;
            $flags[] = sprintf('S&P 500 overnight turun (%+.2f%%)', $sp500Chg);
        }

        $idrChg = $macro['usdidr']['chg_pct'] ?? null;
        $idrClose = $macro['usdidr']['close'] ?? null;
        if ($idrChg !== null && $idrChg >= 0.5) {
            $riskScore += 2;
            $flags[] = sprintf('Rupiah tertekan tajam (%+.2f%% ke Rp%s)', $idrChg, number_format((float) $idrClose, 0, ',', '.'));
        }

        $goldChg = $macro['gold']['chg_pct'] ?? null;
        if ($goldChg !== null && $goldChg <= -2.0) {
            $riskScore += 1;
            $flags[] = sprintf('Emas global terkoreksi tajam (%+.2f%% — waspada emiten logam)', $goldChg);
        }

        if ($riskScore >= 4) {
            $status = 'HIGH_RISK_DEFENSIVE';
            $label = '🔴 Macro Risk Tinggi — Tahan BSJP & Momentum';
            $allowBsjp = false;
            $badgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/40 font-semibold';
        } elseif ($riskScore >= 2) {
            $status = 'CAUTION_SELECTIVE';
            $label = '🟡 Waspada Makro — Selektif & Utamakan Defensif';
            $allowBsjp = false;
            $badgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/40 font-semibold';
        } else {
            $status = 'NORMAL';
            $label = '🟢 Makro & Breadth Kondusif';
            $allowBsjp = true;
            $badgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 font-semibold';
        }

        return [
            'status' => $status,
            'label' => $label,
            'badge_class' => $badgeClass,
            'risk_score' => $riskScore,
            'allow_bsjp' => $allowBsjp,
            'flags' => $flags,
            'breadth' => $breadth,
            'macro' => $macro,
        ];
    }

    /**
     * Fetch cached overnight macro quotes from Yahoo Finance (30m cache; safe empty array in tests/offline).
     *
     * @return array<string, array{close: float, chg_pct: float}>
     */
    public function fetchMacroSnapshot(): array
    {
        if (app()->runningUnitTests()) {
            return [];
        }

        return Cache::store('file')->remember('market:macro-snapshot:v1', now()->addMinutes(30), function () {
            $out = [];
            foreach (self::MACRO_SYMBOLS as $key => $sym) {
                try {
                    $resp = Http::timeout(4)->withHeaders(['User-Agent' => 'Mozilla/5.0'])
                        ->get('https://query2.finance.yahoo.com/v8/finance/chart/'.urlencode($sym), [
                            'range' => '5d',
                            'interval' => '1d',
                        ]);
                    if (! $resp->successful()) {
                        continue;
                    }
                    $closes = array_values(array_filter(
                        $resp->json('chart.result.0.indicators.quote.0.close', []),
                        fn ($v) => is_numeric($v)
                    ));
                    $n = count($closes);
                    if ($n >= 2 && (float) $closes[$n - 2] > 0) {
                        $cur = (float) $closes[$n - 1];
                        $prv = (float) $closes[$n - 2];
                        $out[$key] = [
                            'close' => round($cur, 2),
                            'chg_pct' => round((($cur - $prv) / $prv) * 100.0, 2),
                        ];
                    }
                } catch (Throwable) {
                    continue;
                }
            }

            return $out;
        });
    }
}
