"""
Economic net-cost analysis for BUMI & DEWA joint TP-SL pairs.
READ-ONLY w.r.t. production: imports pipeline functions, writes nothing to storage/.
Uses the pipeline's OWN cost formula (sl_optimizer._cost_pct / simulate_episode:
net = gross - _cost_pct(cost_model)). Because cost is a flat per-episode subtraction,
net_expectancy = gross_expectancy - C exactly. We VALIDATE that before trusting it.
"""
import json, sys, statistics
from pathlib import Path

ROOT = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app")
sys.path.insert(0, str(ROOT))
import quant.trading_research.sl_optimizer as slo

# --- cost scenarios (round-trip %). Mapping -> pipeline keys summed by _cost_pct:
#     entry_fee_pct + exit_fee_pct + exit_tax_pct + entry_slippage_pct + exit_slippage_pct
# IDX sell-tax folded into sell fee per brief; exit_tax_pct=0 to avoid double count.
SCENARIOS = {
    "LOW":  {"entry_fee_pct":0.10,"exit_fee_pct":0.20,"exit_tax_pct":0.0,"entry_slippage_pct":0.10,"exit_slippage_pct":0.10},
    "MID":  {"entry_fee_pct":0.15,"exit_fee_pct":0.25,"exit_tax_pct":0.0,"entry_slippage_pct":0.20,"exit_slippage_pct":0.20},
    "HIGH": {"entry_fee_pct":0.19,"exit_fee_pct":0.29,"exit_tax_pct":0.0,"entry_slippage_pct":0.30,"exit_slippage_pct":0.30},
}
C = {k: slo._cost_pct(v) for k,v in SCENARIOS.items()}

def per_episode_gross(episodes, tp_pct, candidate, same_day="stop_first"):
    """Re-simulate one pair via pipeline; return per-episode GROSS realized returns."""
    out=[]
    for ep in episodes:
        sl = slo.sl_pct_for_candidate(ep, candidate)
        if sl is None: continue
        sim = slo.simulate_episode(ep, sl, tp_pct, same_day)   # cost_model=None -> gross
        if sim["first_hit"]=="ambiguous": continue
        out.append(float(sim["gross_realized_return_pct"]))
    return out

def report(ticker):
    art = json.load(open(ROOT/f"storage/app/trading_research/sl_optimizer/{ticker}_sl_optimizer_v1_1.json"))
    eps_path = ROOT/f"storage/app/trading_research/episodes/{ticker}_trade_episodes_v1.json"
    episodes = slo.load_episode_artifact(eps_path, ticker)["episodes"]
    matrix = art["joint_tp_sl_matrix"]
    gross_exps = [p["expectancy_pct"] for p in matrix]
    best = max(matrix, key=lambda p:p["expectancy_pct"])
    print(f"\n{'='*70}\n{ticker}\n{'='*70}")
    print(f"gross pairs={len(matrix)}  max_gross_exp={max(gross_exps):.4f}  "
          f"best_pair tp={best['tp_pct']} sl={best['sl_candidate']} n={best['episode_count']}")

    # --- VALIDATION: pipeline net == gross - C on real episodes (clear cache!) ---
    cand = best["sl_candidate"]; tp = best["tp_pct"]
    slo.SIM_CACHE.clear()
    g = per_episode_gross(episodes, tp, cand)
    # now run pipeline WITH a nonzero cost on same pair, compare episode-level
    slo.SIM_CACHE.clear()
    cm = SCENARIOS["MID"]; c = slo._cost_pct(cm)
    net_pipe=[]
    for ep in episodes:
        sl = slo.sl_pct_for_candidate(ep, cand)
        if sl is None: continue
        sim = slo.simulate_episode(ep, sl, tp, "stop_first", cm)
        if sim["first_hit"]=="ambiguous": continue
        net_pipe.append(float(sim["net_realized_return_pct"]))
    slo.SIM_CACHE.clear()
    max_err = max(abs((gi-c)-ni) for gi,ni in zip(g,net_pipe))
    print(f"[VALIDATION] pipeline net vs (gross-C) max abs err = {max_err:.10f}  "
          f"(mean gross={statistics.mean(g):.4f}, mean net_pipe={statistics.mean(net_pipe):.4f}, "
          f"gross-C={statistics.mean(g)-c:.4f})  C_MID={c}")

    # --- TABLE: per scenario, net = gross - C for all 96 pairs ---
    print(f"\n  scenario  round_trip%  #net_pos/96   best_net_exp%   survive?")
    print(f"  GROSS     0.00         {sum(1 for e in gross_exps if e>0)}/96          {max(gross_exps):+.4f}         (baseline)")
    for name in ["LOW","MID","HIGH"]:
        cc = C[name]
        npos = sum(1 for e in gross_exps if e - cc > 0)
        best_net = max(gross_exps) - cc
        surv = "YA" if best_net > 0 else "TIDAK"
        print(f"  {name:<8}  {cc:.2f}         {npos}/96          {best_net:+.4f}         {surv}")

    # --- break-even round-trip cost = max gross expectancy ---
    print(f"\n  BREAK-EVEN round-trip cost (best pair) = {max(gross_exps):.4f}%")

    # --- extreme-winner-on-NET for the best pair, MID scenario ---
    print(f"\n  Extreme-winner-on-NET (best pair tp={tp} sl={cand}):")
    for name in ["LOW","MID","HIGH"]:
        cc = C[name]
        net = sorted([gi - cc for gi in g], reverse=True)
        n = len(net); k = max(1, int(n*0.05))
        full = statistics.mean(net)
        excl = statistics.mean(net[k:]) if n-k>0 else float('nan')
        excl_best = statistics.mean(net[1:]) if n>1 else float('nan')
        print(f"    {name:<5} C={cc:.2f}: net_exp_full={full:+.4f}  "
              f"excl_top1={excl_best:+.4f}  excl_top5%({k})={excl:+.4f}  "
              f"-> {'POSITIF' if full>0 else 'NEGATIF'} full / "
              f"{'POSITIF' if excl>0 else 'NEGATIF'} excl-top5%")

for t in ["BUMI","DEWA"]:
    report(t)
