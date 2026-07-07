<?php

namespace App\Services\Research;

use Illuminate\Support\Facades\File;

/**
 * Read-only reference layer for the BUMI/DEWA trading-research artifacts under
 * storage/app/trading_research/ and output/trading_research/reports/. This does
 * not compute anything live; it surfaces the frozen conclusions from
 * quant/trading_research/run_regime_and_longer_hold_net_cost_experiment.py and
 * the reentry-research artifacts so the DSS can show them with the same
 * research-only caveats the underlying research already carries.
 */
class VolatileStockTradingResearchService
{
    public const SUPPORTED_TICKERS = ['BUMI', 'DEWA'];

    public function referenceFor(string $tickerCode): ?array
    {
        $ticker = strtoupper(trim($tickerCode));
        if (! in_array($ticker, self::SUPPORTED_TICKERS, true)) {
            return null;
        }

        return [
            'ticker' => $ticker,
            'net_cost_verdict' => $this->netCostVerdict($ticker),
            'pullback_reference' => $this->pullbackReference($ticker),
        ];
    }

    /**
     * @return array<string, mixed>
     */
    protected function netCostVerdict(string $ticker): array
    {
        $path = base_path('output/trading_research/reports/BUMI_DEWA_v3_regime_longer_hold_experiment.json');
        if (! File::exists($path)) {
            return ['available' => false];
        }

        $data = json_decode((string) File::get($path), true);
        $variants = is_array($data) ? ($data['tickers'][$ticker] ?? null) : null;
        if (! is_array($variants)) {
            return ['available' => false];
        }

        $baseline = $variants['baseline_all_episodes'] ?? null;
        $experimentalVariant = null;
        $experimentalResult = null;
        foreach ($variants as $name => $result) {
            if (($result['verdict'] ?? null) === 'ALIVE_robust_edge_beats_naive_hold') {
                $experimentalVariant = $name;
                $experimentalResult = $result;
                break;
            }
        }

        return [
            'available' => true,
            'baseline_verdict' => $baseline['verdict'] ?? null,
            'has_experimental_candidate' => $experimentalVariant !== null,
            'experimental_candidate_variant' => $experimentalVariant,
            'experimental_candidate' => $experimentalResult,
            'oos_validation' => $this->oosValidation($ticker),
        ];
    }

    /**
     * Result of the pre-registered out-of-sample walk-forward graduation test for the
     * experimental candidate. A failed test retires the candidate: the DSS must stop
     * presenting it as a live research lead.
     *
     * @return array<string, mixed>
     */
    protected function oosValidation(string $ticker): array
    {
        $path = base_path('output/trading_research/reports/BUMI_DEWA_candidate_oos_walkforward_validation.json');
        if (! File::exists($path)) {
            return ['available' => false];
        }

        $data = json_decode((string) File::get($path), true);
        $primary = is_array($data) ? ($data['tickers'][$ticker]['primary_split_70_30'] ?? null) : null;
        if (! is_array($primary)) {
            return ['available' => false];
        }

        return [
            'available' => true,
            'passed' => (bool) ($primary['all_criteria_pass'] ?? false),
            'criteria' => $primary['pre_registered_criteria'] ?? null,
            'oos_net_expectancy' => $primary['oos_selected_pair']['net_expectancy'] ?? null,
            'naive_buy_hold_expectancy' => $primary['oos_naive_buy_hold_same_horizon']['expectancy_pct'] ?? null,
            'test_window' => $primary['test_window'] ?? null,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    protected function pullbackReference(string $ticker): array
    {
        $path = storage_path("app/trading_research/reentry/{$ticker}_reentry_research_v1_1.json");
        if (! File::exists($path)) {
            return ['available' => false];
        }

        $data = json_decode((string) File::get($path), true);
        if (! is_array($data)) {
            return ['available' => false];
        }

        return [
            'available' => true,
            'status' => $data['quality']['status'] ?? null,
            'usable_for_decision' => $data['quality']['usable_for_decision'] ?? null,
            'usable_for_reentry_research' => $data['quality']['usable_for_reentry_research'] ?? null,
            'pullback_candidate' => $data['best_candidates']['best_after_stop_candidate'] ?? null,
            'episode_count' => $data['quality']['episode_count'] ?? null,
            'warnings' => $data['quality']['warnings'] ?? [],
        ];
    }
}
