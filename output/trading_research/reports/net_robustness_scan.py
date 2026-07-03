"""
Scan ALL 96 joint pairs per ticker: at MID cost, find pairs that are BOTH
net-positive AND robust to removing the top-5% winners (extreme-winner test).
Reuses pipeline simulate_episode for per-episode gross; net = gross - C (validated exact).
Writes nothing to storage/.
"""
import json, sys, statistics
from pathlib import Path
ROOT = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app")
sys.path.insert(0, str(ROOT))
import quant.trading_research.sl_optimizer as slo

C_MID = 0.80  # validated round-trip cost

def per_episode_gross(episodes, tp_pct, cand):
    out=[]
    for ep in episodes:
        sl = slo.sl_pct_for_candidate(ep, cand)
        if sl is None: continue
        sim = slo.simulate_episode(ep, sl, tp_pct, "stop_first")
        if sim["first_hit"]=="ambiguous": continue
        out.append(float(sim["gross_realized_return_pct"]))
    return out

for ticker in ["BUMI","DEWA"]:
    art = json.load(open(ROOT/f"storage/app/trading_research/sl_optimizer/{ticker}_sl_optimizer_v1_1.json"))
    episodes = slo.load_episode_artifact(ROOT/f"storage/app/trading_research/episodes/{ticker}_trade_episodes_v1.json", ticker)["episodes"]
    slo.SIM_CACHE.clear()
    rows=[]
    for p in art["joint_tp_sl_matrix"]:
        g = per_episode_gross(episodes, p["tp_pct"], p["sl_candidate"])
        if not g: continue
        net = sorted([gi - C_MID for gi in g], reverse=True)
        n=len(net); k=max(1,int(n*0.05))
        full=statistics.mean(net)
        excl=statistics.mean(net[k:]) if n-k>0 else float('nan')
        rows.append((p["tp_pct"], p["sl_candidate"], full, excl, n))
    netpos=[r for r in rows if r[2]>0]
    robust=[r for r in netpos if r[3]>0]   # net-pos AND survives top-5% removal
    print(f"\n{ticker} @ MID (C={C_MID}): pairs evaluated={len(rows)}  net-positive={len(netpos)}  "
          f"net-pos AND robust(excl top5%>0)={len(robust)}")
    # show best few by robust (excl-top5%) net expectancy
    for r in sorted(rows, key=lambda x:-x[3])[:5]:
        tag = "ROBUST" if (r[2]>0 and r[3]>0) else ("netpos-fragile" if r[2]>0 else "net-neg")
        print(f"   tp={r[0]:<5} sl={str(r[1]):<34} net_full={r[2]:+.4f} net_excl_top5%={r[3]:+.4f} n={r[4]}  [{tag}]")
