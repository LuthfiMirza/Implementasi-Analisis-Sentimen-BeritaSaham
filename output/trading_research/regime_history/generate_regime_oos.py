"""
TAHAP 2 + 2b: Walk-forward (expanding-window) OUT-OF-SAMPLE regime move/no_move
predictions for BUMI & DEWA, then skill validation vs base rate / majority class.

POINT-IN-TIME: reuses production build_folds(); for fold with train_end T, model is
fit ONLY on rows with reference_date <= T and predicts the forward test window (> T).
Scaler is fit on train only. => no look-ahead.

MOVE DEFINITION (pre-registered, NOT tuned): move = |future_return_5d| > 0.005 (0.5%).
Same threshold as production label (run_special_volatile_stock_research.py:302).

Writes ONLY under output/trading_research/regime_history/. Production untouched.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, brier_score_loss, confusion_matrix, accuracy_score

ROOT = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app")
sys.path.insert(0, str(ROOT))
from quant.train_prediction_models import build_folds

OUT = ROOT/"output/trading_research/regime_history"
MOVE_THRESHOLD = 0.005            # |future_return_5d| > 0.5%  (pre-registered)
MIN_TRAIN_DAYS = 252
TEST_WINDOW_DAYS = 126
FEATURES = ["return_1d","return_3d","return_5d","return_20d","atr14_pct","atr_ratio",
            "volume_ratio_5d","volume_ratio_20d","price_vs_ema20_pct","price_vs_ema50",
            "rsi_slope_5d","return_5d_cross_section_rank","volume_spike_flag",
            "market_regime_bullish","regime_duration"]

def run(ticker):
    df = pd.read_csv(ROOT/f"output/prediction_research/dataset_{ticker.lower()}_special.csv")
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    feats = [c for c in FEATURES if c in df.columns]
    df = df.dropna(subset=["future_return_5d"]+feats).sort_values("reference_date").reset_index(drop=True)
    df["y_move"] = (df["future_return_5d"].abs() > MOVE_THRESHOLD).astype(int)   # 1=move
    unique_dates = sorted(df["reference_date"].unique())
    folds = build_folds([pd.Timestamp(d) for d in unique_dates], MIN_TRAIN_DAYS, TEST_WINDOW_DAYS)

    rows = []
    for f in folds:
        tr = df[df["reference_date"] <= f.train_end]
        te = df[(df["reference_date"] >= f.test_start) & (df["reference_date"] <= f.test_end)]
        if tr["y_move"].nunique() < 2 or len(te)==0: continue
        sc = StandardScaler().fit(tr[feats])
        clf = LogisticRegression(max_iter=1000, random_state=42).fit(sc.transform(tr[feats]), tr["y_move"])
        proba = clf.predict_proba(sc.transform(te[feats]))[:, list(clf.classes_).index(1)]
        train_majority = int(tr["y_move"].mode()[0])   # point-in-time majority baseline
        for dt, yt, pr in zip(te["reference_date"], te["y_move"], proba):
            rows.append({"reference_date": dt.strftime("%Y-%m-%d"),
                         "train_end": f.train_end.strftime("%Y-%m-%d"),
                         "y_true_move": int(yt), "proba_move": float(pr),
                         "pred_move": int(pr>=0.5), "train_majority_pred": train_majority})
    hist = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    hist.to_csv(OUT/f"{ticker}_regime_oos_history.csv", index=False)

    # ---- SKILL VALIDATION (TAHAP 2b) ----
    y = hist["y_true_move"].values; p = hist["proba_move"].values; yhat = hist["pred_move"].values
    base_rate = float(y.mean())                              # P(actual move) OOS
    acc = float(accuracy_score(y, yhat))
    # honest majority baseline: predict window-level point-in-time train majority each row
    acc_majority_pit = float((hist["train_majority_pred"].values == y).mean())
    # naive constant global-majority baseline
    global_majority = 1 if base_rate>=0.5 else 0
    acc_majority_global = float((np.full_like(y, global_majority) == y).mean())
    auc = float(roc_auc_score(y, p)) if len(np.unique(y))>1 else float("nan")
    brier = float(brier_score_loss(y, p))
    brier_baserate = float(brier_score_loss(y, np.full_like(p, base_rate)))
    cm = confusion_matrix(y, yhat, labels=[1,0])            # rows/cols order: move, no_move
    meta = {"ticker": ticker, "n_oos": int(len(hist)),
            "oos_date_range": [hist["reference_date"].min(), hist["reference_date"].max()],
            "n_folds_used": int(hist["train_end"].nunique()),
            "move_definition": "abs(future_return_5d) > %.4f" % MOVE_THRESHOLD,
            "features_used": feats, "window_policy": f"expanding min_train={MIN_TRAIN_DAYS}d test={TEST_WINDOW_DAYS}d",
            "base_rate_move": base_rate, "accuracy": acc,
            "accuracy_majority_pointintime": acc_majority_pit,
            "accuracy_majority_global": acc_majority_global,
            "auc": auc, "brier": brier, "brier_baserate": brier_baserate,
            "brier_skill_score": float(1 - brier/brier_baserate) if brier_baserate else None,
            "confusion_matrix_move_nomove": {"tp_move": int(cm[0,0]), "fn_move": int(cm[0,1]),
                                              "fp_move": int(cm[1,0]), "tn_nomove": int(cm[1,1])}}
    (OUT/f"{ticker}_regime_skill.json").write_text(json.dumps(meta, indent=2))
    return meta

def verdict(m):
    auc, acc, majp = m["auc"], m["accuracy"], m["accuracy_majority_pointintime"]
    bss = m["brier_skill_score"]
    if auc >= 0.58 and acc > majp + 0.02 and (bss or 0) > 0.02: return "[SKILL]"
    if auc <= 0.53 or acc <= majp + 0.005 or (bss or 0) <= 0.0: return "[NO SKILL]"
    return "[MARGINAL]"

print(f"{'ticker':6} {'n_oos':>6} {'base':>6} {'acc':>6} {'majPIT':>7} {'majGLB':>7} {'AUC':>6} {'Brier':>7} {'BrierBR':>7} {'BSS':>7}  verdict")
results={}
for t in ["BUMI","DEWA"]:
    m = run(t); results[t]=m
    print(f"{t:6} {m['n_oos']:>6} {m['base_rate_move']:.3f}  {m['accuracy']:.3f}  {m['accuracy_majority_pointintime']:.3f}  "
          f"{m['accuracy_majority_global']:.3f}  {m['auc']:.3f}  {m['brier']:.4f}  {m['brier_baserate']:.4f}  "
          f"{(m['brier_skill_score'] or 0):+.3f}  {verdict(m)}")
    cm=m["confusion_matrix_move_nomove"]
    print(f"       confusion: TP_move={cm['tp_move']} FN_move={cm['fn_move']} FP_move={cm['fp_move']} TN_nomove={cm['tn_nomove']}")

# point-in-time proof samples
print("\nPOINT-IN-TIME PROOF (train_end < reference_date, sample):")
for t in ["BUMI","DEWA"]:
    h=pd.read_csv(OUT/f"{t}_regime_oos_history.csv")
    s=h.iloc[[0, len(h)//2, len(h)-1]]
    for _,r in s.iterrows():
        ok = r["train_end"] < r["reference_date"]
        print(f"  {t}: train_end={r['train_end']} < pred_date={r['reference_date']} -> {ok}")
