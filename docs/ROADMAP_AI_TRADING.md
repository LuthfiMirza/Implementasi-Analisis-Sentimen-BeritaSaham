# AI Trading Decision Support Roadmap

Last updated: 2026-07-02
Status: Sprint 18 completed — Position Management Risk and Review Plan Contract Foundation
Owner: AI Trading DSS workstream

This document is the single source of truth for the AI Trading Decision Support System implementation. Any architecture change must update this roadmap first, then implementation may follow. The existing Prediction Engine must remain stable; the trading system is a new layer built above it.

## 1. Vision

The final system is an AI Trading Decision Support System for BUMI and DEWA that turns raw prediction output into explainable trading decisions. The system must never rely on arbitrary static rules such as fixed TP 20% or buy after a fixed decline. Trading parameters must come from historical research artifacts, walk-forward validation, optimizer outputs, and ongoing outcome evaluation.

### 1.1 Prediction Engine

Purpose: estimate directional or regime probability.

Existing scope:
- BUMI Technical predicts direction for BUMI.
- DEWA Technical predicts direction for DEWA.
- DEWA Regime predicts `move` / `no_move` for DEWA, not price direction.
- General V6A/V6B prediction remains available for non-special stocks.

Responsibilities:
- Produce `predicted_direction`, `predicted_regime`, probability, model metadata, and feature basis.
- Stay isolated from trading-plan logic.
- Continue using the stable FastAPI model serving contract.

Non-responsibilities:
- It must not choose TP, SL, entry zones, position size, or trading action.

### 1.2 Research Engine

Purpose: transform historical data into reusable decision evidence.

Responsibilities:
- Build event datasets from historical BUY-like events.
- Run walk-forward trade research without random train/test split.
- Calculate return horizons, MFE, MAE, drawdown, TP hit rates, SL outcomes, holding periods, pullback, recovery, and re-entry statistics.
- Emit versioned JSON artifacts with schema version, generated timestamp, ticker scope, fold summary, and recommended parameters.

### 1.3 Decision Engine

Purpose: combine prediction, research evidence, current technical state, sentiment, market regime, and open-trade state into one trading action.

Actions:
- `BUY`
- `ACCUMULATE`
- `WAIT`
- `HOLD`
- `PARTIAL_TAKE_PROFIT`
- `FULL_TAKE_PROFIT`
- `SELL`
- `CUT_LOSS`
- `BUY_BACK`
- `NO_TRADE`

Output includes confidence, recommendation quality, risk level, entry zone, TP, SL, expected return, risk reward, holding days, expected drawdown, expected win rate, historical expectancy, reasons, warnings, and action instructions.

### 1.4 Learning Engine

Purpose: evaluate completed decisions and trades.

Responsibilities:
- Compare planned TP/SL/hold/re-entry against realized outcome.
- Identify whether exit was early, late, or invalidated.
- Track failed indicators and unstable confidence components.
- Recommend changes for future research or calibration.

### 1.5 Notification Engine

Purpose: convert decision states into actionable alerts.

Triggers:
- TP hit.
- SL hit.
- Price enters entry zone.
- Price enters re-entry zone.
- Probability or decision action improves.
- Breakout or breakdown.
- Open trade requires partial or full exit.

### 1.6 Dashboard

Purpose: expose decisions and evidence to users.

Panels:
- Decision summary.
- Trade plan.
- Confidence breakdown.
- Risk profile.
- Research evidence.
- Reasons and warnings.
- Open trade state.
- Notification status.

## 2. Existing Architecture

### 2.1 Existing Components

Prediction page and Laravel orchestration:
- `app/Http/Controllers/PredictionController.php` builds price/article context, features, and predictions.
- `app/Http/Controllers/PredictionController.php:88` selects prediction variants by ticker.
- `app/Http/Controllers/PredictionController.php:91` calls `bumi_technical` for BUMI.
- `app/Http/Controllers/PredictionController.php:95` and `app/Http/Controllers/PredictionController.php:96` call `dewa_regime` and `dewa_technical` for DEWA.

FastAPI prediction serving:
- `quant/prediction_api.py` contains model loading and inference.
- `quant/prediction_api.py:115` defines production stores.
- `quant/prediction_api.py:126` to `quant/prediction_api.py:131` map BUMI/DEWA variants to production `.joblib` and metadata files.
- `quant/prediction_api.py:265` reads `feature_columns` from metadata.
- `quant/prediction_api.py:269` calls `predict()`.
- `quant/prediction_api.py:271` calls `predict_proba()`.
- `quant/prediction_api.py:276` returns regime-specific output for `dewa_regime`.

Feature engineering:
- `app/Services/Prediction/ResearchPredictionFeatureService.php` defines point-in-time feature columns.
- Existing features include returns, ATR, volume ratio, EMA distance, RSI slope, market regime, and sentiment features.

Decision support indicators:
- `app/Services/Analytics/DecisionSupportService.php` already calculates MACD, Bollinger, Stochastic, OBV, ADX, ATR, VWAP, candlestick patterns, support/resistance, and score components.
- These calculations are useful but must not become static trading rules without research artifacts.

Backtest:
- `app/Services/Analytics/BacktestService.php` validates directional prediction and special model behavior.
- It does not yet model complete trade lifecycle events.

Trade journal:
- `database/migrations/2026_04_12_020000_create_trades_table.php` stores entry, stop loss, target, RR, DSS score, indicators snapshot, status, result, and PnL.
- `app/Models/Trade.php` supports open/closed trade state and PnL calculation.

Retraining:
- `app/Console/Commands/RetrainVolatilePredictionModelsCommand.php` retrains BUMI/DEWA volatile prediction artifacts and writes retrain history.

### 2.2 Missing Components

Missing for enterprise-grade AI Trading DSS:
- Versioned trade research artifacts.
- Artifact reader service.
- Walk-forward trade research engine.
- TP optimizer artifact.
- SL optimizer artifact.
- Re-entry research artifact.
- Trading decision service.
- Confidence engine.
- Reason engine.
- Risk engine.
- Trade plan engine.
- Notification engine.
- Learning engine.
- Adaptive weight calibration.
- Portfolio ranking engine.
- Stock personality model.

### 2.3 Reusable Components

Reusable without large changes:
- `PredictionController` prediction flow.
- `ApiPredictionController` API contract.
- `quant/prediction_api.py` model serving.
- `ResearchPredictionFeatureService` feature columns.
- `DecisionSupportService` technical snapshot calculations.
- `BacktestService` as reference for special BUMI/DEWA model integration.
- `Trade` model and trade journal.
- `WatchlistController` and watchlist data for future portfolio ranking.
- `StockPrice::canonicalize()` for daily OHLCV cleanup.

### 2.4 New Components Required

New components must live in a separate layer:
- `app/Services/Research/ResearchArtifactService.php`
- `app/Services/Trading/TradingDecisionService.php`
- `app/Services/Trading/ConfidenceEngineService.php`
- `app/Services/Trading/ReasonEngineService.php`
- `app/Services/Trading/RiskEngineService.php`
- `app/Services/Trading/TradePlanService.php`
- `app/Services/Trading/NotificationSignalService.php`
- `app/Services/Trading/PortfolioRankingService.php`
- `quant/trading_research/*`
- `storage/app/trading_research/*`
- Database migrations for decision, alert, artifact, and learning records.

## 3. New Architecture

```text
Existing OHLCV + News + Sentiment + Trade Journal
        ↓
Existing Feature Engineering
        ↓
Existing Prediction Engine
        ↓
Research Engine
- Walk-forward artifacts
- TP optimizer artifacts
- SL optimizer artifacts
- Re-entry artifacts
        ↓
Decision Engine
- Action selection
- Trade plan
- Confidence breakdown
- Risk calculation
- Reason generation
        ↓
Notification Engine
- TP/SL/re-entry/breakout alerts
        ↓
Learning Engine
- Outcome evaluation
- Failed reason analysis
        ↓
Calibration Engine
- Adaptive confidence weights
- Stock personality adjustments
        ↓
Dashboard
- Explainable trading decision support
```

Rules:
- Prediction remains a lower-level signal provider.
- Research artifacts are mandatory evidence for aggressive trading actions.
- If research artifacts are missing or stale, decision must downgrade to `WAIT` or `NO_TRADE`.
- Every artifact and decision output must declare `schema_version`.

## 4. Milestones

### Milestone 1 — Research Artifact Foundation

Purpose:
- Establish the storage, schema convention, example artifacts, and PHP artifact reader.

Output:
- `storage/app/trading_research/examples/*.json`
- `app/Services/Research/ResearchArtifactService.php`
- Unit tests for artifact loading, validation, latest selection, and unavailable state.

Dependencies:
- Laravel filesystem helpers.
- No dependency on dashboard, notification, or model retraining.

Files created:
- `app/Services/Research/ResearchArtifactService.php`
- `tests/Unit/ResearchArtifactServiceTest.php`
- `storage/app/trading_research/examples/walk_forward_bumi_v1.json`
- `storage/app/trading_research/examples/tp_optimizer_bumi_v1.json`
- `storage/app/trading_research/examples/reentry_bumi_v1.json`

Files changed:
- `docs/ROADMAP_AI_TRADING.md`

Acceptance criteria:
- Service returns artifact payload when schema is valid.
- Service rejects invalid schema version.
- Service returns unavailable metadata when artifact is missing.
- Tests pass without database or FastAPI.

Risk:
- Schema drift if artifacts are not versioned.

Complexity:
- Low.

Status:
- Completed on 2026-07-01.

### Milestone 2 — Walk Forward Research Artifact Generator

Purpose:
- Generate walk-forward trade research from historical BUMI/DEWA data.

Output:
- Python scripts under `quant/trading_research/`.
- Event dataset artifacts under `storage/app/trading_research/events/`.

Dependencies:
- Milestone 1 schema.
- Existing OHLCV and prediction research datasets.

Files created:
- `quant/trading_research/__init__.py`
- `quant/trading_research/walk_forward_event_dataset.py`
- `quant/test_walk_forward_event_dataset.py`

Files changed:
- Optional Artisan command in later milestone.

Acceptance criteria:
- Each historical BUY signal becomes one event record.
- Event features are point-in-time at entry date.
- Future OHLCV is used only to calculate holding-period outcome metrics.
- No model training, TP optimizer, SL optimizer, decision engine, confidence engine, dashboard, notification, or learning engine is created.
- Output includes entry price/date, holding days, highest/lowest/exit price, return, MFE, MAE, drawdown, recovery, ATR, RSI, MACD, ADX, VWAP, volume ratio, market regime, sentiment, prediction metadata, and trade outcome.
- Validator rejects missing required fields, invalid schema version, missing ticker, duplicate events, missing OHLCV-backed prices, and invalid prices.

Risk:
- Look-ahead bias if event features use future data.

Complexity:
- Medium.

Status:
- Sprint 2 completed on 2026-07-01 for the walk-forward event dataset foundation. Full TP/SL optimizer research remains deferred to later sprints.

Event dataset schema:
- Schema version: `walk_forward_event_dataset_v1`.
- Artifact type: `walk_forward_event_dataset`.
- Artifact root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `config`, `events`, `quality`.
- Required event fields: `entry_date`, `entry_price`, `holding_days`, `highest_price`, `lowest_price`, `exit_price`, `return_pct`, `mfe_pct`, `mae_pct`, `drawdown_pct`, `recovery_pct`, `atr`, `rsi`, `macd`, `adx`, `vwap`, `volume_ratio`, `market_regime`, `news_sentiment`, `prediction_probability`, `prediction_variant`, `trade_outcome`.
- Output naming: `{TICKER}_events_v1.json`, for example `BUMI_events_v1.json` and `DEWA_events_v1.json`.
- Execution example: `python3 -m quant.trading_research.walk_forward_event_dataset --ticker BUMI --ohlcv data/stocks/BUMI.csv --prediction-history output/prediction_research/tickers/BUMI.csv --output-dir storage/app/trading_research/events`.

### Milestone 3 — TP Optimizer Research

Purpose:
- Generate historical take-profit research evidence from the walk-forward event dataset.

Output:
- Event dataset quality reports under `storage/app/trading_research/quality/`.
- TP optimizer artifacts under `storage/app/trading_research/tp_optimizer/`.

Dependencies:
- Milestone 2 event dataset artifacts.
- No dependency on Prediction Engine, FastAPI, dashboard, database, trade journal, decision engine, confidence engine, notification, or learning engine.

Files created:
- `quant/trading_research/artifact_utils.py`
- `quant/trading_research/event_dataset_quality.py`
- `quant/trading_research/tp_optimizer.py`
- `quant/test_event_dataset_quality.py`
- `quant/test_tp_optimizer.py`
- `docs/adr/ADR-001-research-artifact-format.md`
- `docs/adr/ADR-002-walk-forward-event-dataset.md`
- `docs/adr/ADR-003-tp-optimizer-selection-policy.md`

Files changed:
- `docs/ROADMAP_AI_TRADING.md`

Acceptance criteria:
- Quality gate validates BUMI and DEWA event artifacts before TP optimization.
- Quality gate writes deterministic JSON reports with event counts, duplicate counts, overlapping holding periods, missing values, invalid values, distributions, price consistency, look-ahead leakage risk notes, and insufficient future OHLCV counts.
- TP candidates come from config or CLI arguments, not production hardcoding.
- Realized return policy is explicit: TP hit realizes the candidate TP; timeout realizes the event exit return.
- Walk-forward folds are chronological and never shuffled.
- Selected TP is deterministic, transparent, and based on configured score weights.
- Segment output is limited to market regime, volatility bucket, and prediction probability bucket, with insufficient samples marked unusable.
- Artifact validator rejects invalid schema, duplicate candidates/folds, bad percentages, fold leakage, selected TP outside candidates, quality inconsistency, and source hash mismatch.
- No SL optimizer, decision engine, confidence engine, dashboard, notification, learning engine, migration, or PredictionController integration is created.

Risk:
- Overfitting TP selection to in-sample hit rate if walk-forward validation and downside metrics are ignored.

Complexity:
- Medium.

Status:
- TP Optimizer Prototype Completed on 2026-07-01. Unit tests passed and BUMI/DEWA quality reports plus TP optimizer artifacts were generated and validated, but downstream audit identified quality-policy hardening required before Sprint 4.
- Sprint 3 quality gate found one DEWA price consistency issue from Sprint 2 event construction. The Sprint 2 builder was fixed so `highest_price` and `lowest_price` always include entry and exit prices, a regression test was added, and BUMI/DEWA event artifacts were regenerated before TP optimization.

Quality gate outputs:
- `storage/app/trading_research/quality/BUMI_event_quality_v1.json`: valid, 6177 events, 0 duplicate events, 0 invalid prices, 0 price consistency violations, 20 shorter future-OHLCV events, 6176 overlapping holding periods.
- `storage/app/trading_research/quality/DEWA_event_quality_v1.json`: valid, 4554 events, 0 duplicate events, 0 invalid prices, 0 price consistency violations, 20 shorter future-OHLCV events, 4553 overlapping holding periods.

TP optimizer outputs:
- `storage/app/trading_research/tp_optimizer/BUMI_tp_optimizer_v1.json`: selected TP 5.0%, validation expectancy -0.312488%, validation hit rate 0.670243, fold stability 1.0, quality valid.
- `storage/app/trading_research/tp_optimizer/DEWA_tp_optimizer_v1.json`: selected TP 5.0%, validation expectancy 0.913471%, validation hit rate 0.356318, fold stability 1.0, quality valid.

TP optimizer schema:
- Schema version: `tp_optimizer_v1`.
- Artifact type: `tp_optimizer`.
- Artifact root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `generator_version`, `config`, `source`, `candidates`, `folds`, `selected`, `segments`, `quality`, `notes`.
- Source fields: `event_artifact_path`, `event_schema_version`, `event_generated_at`, `event_count`, `source_checksum`, `data_start`, `data_end`.
- Quality fields: `status`, `usable_for_decision`, `sample_size`, `minimum_sample_size`, `fold_count`, `fold_stability`, `warnings`.
- Return policy: if a candidate TP is reached during the holding period, realized return equals the candidate TP; otherwise realized return equals the event `return_pct`.
- Sprint 4 dependency: SL Optimizer Research must consume the event dataset and TP evidence separately; SL must remain a separate sprint after Sprint 3.

### Milestone 3.1 — TP Optimizer Validation Hardening

Purpose:
- Harden TP optimizer quality policy before any SL optimizer work starts.

Reason:
- Prototype artifacts allowed `usable_for_decision=true` despite negative BUMI out-of-sample expectancy.
- Fold stability only represented selected TP agreement, not economic performance stability.
- Overlapping event windows made raw sample size optimistic.
- Tail events without full future OHLCV were included in optimizer evaluation.
- Zero-return and stale-price behavior required explicit audit.

Output:
- Hardened TP optimizer artifacts under `storage/app/trading_research/tp_optimizer/`.
- Updated quality reports under `storage/app/trading_research/quality/`.
- ADRs for overlapping events and artifact usability policy.

Acceptance criteria:
- `usable_for_decision` is true only when configured usability gates pass: positive minimum validation expectancy, profitable fold ratio, effective sample size, fold count, downside tail, source validity, no leakage, and no critical warnings.
- If no candidate passes, `selected` is null, `best_candidate_by_score` remains available, quality is `research_only` or `not_usable`, and warnings explain the failure.
- Stability metrics are split into `selection_stability`, `expectancy_stability`, `hit_rate_stability`, `drawdown_stability`, `performance_dispersion`, `profitable_fold_ratio`, and `selected_candidate_frequency`.
- Optimizer stores `all_events_analysis` and `non_overlapping_analysis`; default main selection uses `purge_overlapping`.
- Artifact stores raw, eligible, overlapping, purged, cluster, and effective sample counts.
- Events with incomplete future OHLCV are excluded from candidate evaluation and reported in `exclusions`.
- Zero-return and stale-price audit is included and can downgrade usability by config.
- Deterministic confidence intervals are stored with configured random seed.
- Validators accept `selected=null` only when quality is not usable and reject quality inconsistencies.

TP schema hardening:
- Schema version remains `tp_optimizer_v1` with additive fields for compatibility.
- Added fields: `selection_policy`, `usability_policy`, `all_events_analysis`, `non_overlapping_analysis`, `exclusions`, `stability`, `confidence_intervals`, `effective_sample_size`, `best_candidate_by_score`, `critical_warnings`.
- `selected` may be null when `quality.usable_for_decision=false`.

Sprint 4 gate:
- SL Optimizer Research cannot start until Sprint 3.1 tests pass and BUMI/DEWA hardened artifacts are regenerated and validated.

Status:
- Sprint 3.1 completed on 2026-07-01. Hardened TP artifacts were regenerated and validated; both BUMI and DEWA are now `research_only` with `usable_for_decision=false` because effective non-overlapping sample size and fold count are below policy minimums.

Sprint 3.1 hardened artifact summary:
- BUMI: raw events 6177, eligible events 6112, purged events 6110, effective sample size 2, selected null, best candidate by score 30.0%, quality `research_only`.
- DEWA: raw events 4554, eligible events 4521, purged events 4520, effective sample size 1, selected null, best candidate by score 30.0%, quality `research_only`.
- Incomplete future OHLCV exclusions: 20 events per ticker.
- Zero-return rates: BUMI 0.118783, DEWA 0.508516.
- No Sprint 4 work may start until these hardened artifacts are accepted as the Sprint 3.1 baseline.

### Milestone 4 — SL Optimizer Research

### Milestone 3.2 — Trade Episode Dataset and Chronological Path Simulator

Purpose:
- Convert daily BUY observations into executable chronological trade episodes before any further optimizer work.

Reason:
- Sprint 3.1 proved raw BUY observations are not independent trade events. Connected overlap clusters are diagnostic only and must not be treated as a statistical effective sample size.

Output:
- `storage/app/trading_research/episodes/{TICKER}_trade_episodes_v1.json`.
- Regenerated TP optimizer artifacts using `one_position_fixed_horizon` episodes as primary input.

Acceptance criteria:
- Signal observation dataset remains descriptive evidence only.
- Primary trade episode construction uses `one_position_fixed_horizon` and produces no concurrent position.
- `signal_transition` and `fixed_spacing` are available for sensitivity comparison.
- Entry defaults to next available trading-day open and stores entry policy/provenance.
- Episodes store OHLCV reference anchors and checksum rather than bulky embedded paths.
- Chronological simulator determines TP/SL first-hit order from daily rows, with same-day ambiguity policy defaulting to `stop_first`.
- Incomplete future horizon episodes are excluded from optimizer inputs and recorded as `insufficient_future_ohlcv`.
- Walk-forward folds include purge/embargo metadata and leakage checks.
- TP metric nullability is explicit: CI/stability/ratios are null when denominators or sample sizes are insufficient.
- Sprint 4 SL Optimizer remains blocked and not implemented.

Schema:
- Episode schema version: `trade_episode_dataset_v1`.
- Root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `generator_version`, `config`, `source`, `observation_summary`, `episode_summary`, `exclusions`, `episodes`, `quality`, `notes`.
- Episode fields: `episode_id`, `ticker`, `signal_date`, `entry_date`, `entry_price`, `horizon_end_date`, `holding_days`, `complete_horizon`, `sampling_policy`, `source_event_id`, `source_ohlcv_reference`, `prediction_probability`, `prediction_variant`, `market_regime`, `news_sentiment`, `entry_feature_snapshot`, `outcome_summary`.

Status:
- Sprint 3.2 completed on 2026-07-01. Trade episode artifacts were generated for BUMI and DEWA, TP artifacts were regenerated from `one_position_fixed_horizon` episodes, and all tests passed.

Sprint 3.2 artifact summary:
- BUMI: raw observations 6177, signal-transition episodes 1, one-position episodes 309, fixed-spacing episodes 309, complete-horizon episodes 308, incomplete exclusions 1, median episode spacing 28.0, selected TP null, quality `research_only`.
- DEWA: raw observations 4554, signal-transition episodes 1, one-position episodes 228, fixed-spacing episodes 228, complete-horizon episodes 227, incomplete exclusions 1, median episode spacing 29.0, selected TP null, quality `research_only`.
- Regenerated TP artifacts remain not usable for decisions: BUMI fails validation expectancy/profitable fold/CI lower-bound gates; DEWA fails CI lower-bound gate.

### Milestone 4 — SL Optimizer Research

Purpose:
- Generate historical stop-loss research evidence after TP optimizer artifacts exist.
- Sprint 4 scope is Stop-Loss Optimizer Research only. Primary input is the Trade Episode Dataset generated with `one_position_fixed_horizon`. `signal_transition` remains diagnostic because the source event dataset contains BUY observations only. TP artifacts for BUMI and DEWA remain `research_only` and not usable for decision, so SL research must not depend on selected TP.

Output:
- SL optimizer artifacts under `storage/app/trading_research/sl_optimizer/`.
- Standalone SL candidate analysis and joint TP-SL sensitivity matrix.

Schema:
- Schema version: `sl_optimizer_v1`.
- Root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `generator_version`, `config`, `source`, `exclusions`, `standalone_candidates`, `joint_tp_sl_matrix`, `folds`, `stability`, `confidence_intervals`, `best_sl_candidate_by_score`, `best_tp_sl_pair_by_score`, `selected`, `quality`, `warnings`, `notes`.

Quality policy:
- `usable_for_risk_analysis` can be true when standalone downside coverage has sufficient sample/folds.
- `usable_for_decision` requires valid episode and TP source artifacts, positive OOS TP-SL expectancy, CI lower bound above policy minimum, profitable fold ratio, worst-fold limit, enough validation sample/folds, acceptable ambiguity and premature-stop rates, no leakage, no critical warning, and decision-usable TP evidence.
- Because current TP artifacts are `research_only`, Sprint 4 artifacts must default to decision-unusable unless future TP evidence passes quality gates.

Dependencies:
- Milestone 2 event dataset artifacts.
- Milestone 3 TP optimizer artifacts for later combined trade-plan research.
- Milestone 3.2 trade episode artifacts.

Acceptance criteria:
- SL candidates are researched separately from TP candidates.
- No decision engine or dashboard integration is created during this sprint.
- Fixed-percent and ATR-multiple SL families are evaluated from config/CLI.
- Joint TP-SL matrix uses chronological simulator and handles same-day ambiguity with `stop_first` primary policy plus sensitivity evidence.
- Premature stop, recovery-after-stop, loss-avoided, CVaR, downside tails, fold results, source checksums, and nullability are documented.
- Selected remains null when quality gates fail; best standalone and joint candidates remain available for research.

Status:
- SL Optimizer Research Prototype Completed on 2026-07-01. SL optimizer research artifacts were generated for BUMI and DEWA, validators passed, source provenance was recorded, and all research unit tests passed.
- BUMI SL artifact: risk-analysis usable, decision unusable because source TP artifact is not decision usable; selected null.
- DEWA SL artifact: risk-analysis usable, decision unusable because source TP artifact is not decision usable; selected null.

### Milestone 4.1 — Execution and Joint Validation Hardening

Purpose:
- Harden SL/joint TP-SL research for execution realism, ATR provenance, gross/net performance, boundary effects, extreme-winner dependency, and nested validation before Re-entry Research.

Scope:
- Primary inputs remain Trade Episode Dataset and canonical OHLCV.
- TP artifacts may provide schema-valid candidate provenance even when standalone TP is not decision-usable.
- No Laravel integration, production decision layer, dashboard, migration, Prediction Engine, FastAPI, or Re-entry Research is created.

Acceptance criteria:
- ATR provenance is audited from event artifact to episode artifact to SL optimizer; if missing in episode transformation, fix and regenerate impacted artifacts.
- Fixed-percent, ATR, and optional MAE-quantile family quality are reported separately.
- Chronological simulator supports gap-aware stop/target fills and entry-day audit semantics.
- Gross and net returns are reported separately with configurable fee, tax, slippage, and disabled-cost warning.
- Boundary optimum analysis flags lower/upper grid winners and neighboring robustness.
- Extreme-winner dependency metrics are included for each joint pair.
- Nested chronological validation selects candidates on outer-training data only and reports outer validation evidence.
- Joint TP-SL source policy allows schema-valid TP candidate lists for research, but decision usability depends on joint evidence quality.
- `selected` remains null when joint quality gates fail.

Schema:
- Hardened schema version: `sl_optimizer_v1_1`.
- Added fields: `execution_model`, `transaction_cost_model`, `atr_provenance`, `family_quality`, `boundary_analysis`, `extreme_winner_analysis`, `nested_walk_forward`, `gross_metrics`, `net_metrics`, `gap_metrics`, `source_policy`, `best_gross_joint_pair`, `best_net_joint_pair`, `most_frequent_nested_pair`, `selected`, `critical_warnings`.

Status:
- Sprint 4.1 completed on 2026-07-01. Episode artifacts were regenerated to carry ATR snapshots, TP artifacts were regenerated because episode checksums changed, SL artifacts were regenerated as `sl_optimizer_v1_1`, and all research tests passed.
- BUMI: fixed and ATR family risk analysis usable; decision unusable because source TP is not decision usable and execution-cost model is disabled.
- DEWA: fixed family risk analysis usable, ATR family not usable due lower coverage; decision unusable because CI lower bound/extreme-winner/source TP/cost warnings remain.

### Milestone 5 — Re-entry Research

Purpose:
- Research post-exit recovery and one-time re-entry behavior after stop-loss, take-profit, and timeout exits.

Scope:
- Research artifact only; no Laravel integration and no production BUY_BACK action.
- Uses Trade Episode Dataset, SL optimizer evidence, optional TP candidate provenance, and canonical OHLCV.
- Maximum one re-entry per original episode; no martingale, no position-size increase, and constant nominal exposure.

Schema:
- Schema version: `reentry_research_v1`.
- Root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `generator_version`, `config`, `source`, `execution_model`, `transaction_cost_profiles`, `exclusions`, `recovery_after_stop`, `pullback_after_tp`, `continuation_after_timeout`, `candidate_results`, `segments`, `nested_walk_forward`, `stability`, `confidence_intervals`, `extreme_winner_analysis`, `best_candidates`, `selected`, `quality`, `warnings`, `notes`.

Acceptance criteria:
- Streams are separated for after-stop, after-TP, and after-timeout behavior.
- Re-entry metrics report incremental value versus doing nothing.
- Zero-cost and configurable non-zero-cost profiles are stored separately.
- Nested chronological validation uses inner training selection and outer validation evaluation with purge/embargo covering original horizon plus extension window.
- ATR and percentage candidate family coverage are reported separately.
- `selected` remains null unless decision-grade gates pass.

Status:
- Re-entry Research Prototype Completed on 2026-07-01. BUMI and DEWA `reentry_research_v1` artifacts were generated and validated, with selected remaining null and all research tests passing. Contract hardening is required before Artifact Registry work.

### Milestone 5.1 — Re-entry Contract and Validation Hardening

Purpose:
- Harden re-entry source schema policy, episode accounting reconciliation, recovery timing, stream-specific sample policy, family quality, cost provenance, and extreme-winner semantics.

Scope:
- Research artifact only. No Artifact Registry, Trading Decision Service, Laravel integration, dashboard, migration, or production decision layer is created.

Schema:
- Schema version: `reentry_research_v1_1`.
- Added fields: `episode_accounting`, `stream_accounting`, `family_quality`, `recovery_timing`, `source_schema_policy`, `cost_profile`, `extreme_winner_interpretation`, `per_stream_nested_results`, and `validation_summary`.

Acceptance criteria:
- Source SL schema must be `sl_optimizer_v1_1` by artifact root schema, not filename.
- All source episodes reconcile through classified stop/TP/timeout, exclusions, or unclassified count.
- Recovery count and median recovery days are consistent.
- Stream denominators and candidate selection are independent for after-stop, after-TP, and after-timeout.
- Minimum sample policy nulls best candidates for insufficient streams while preserving descriptive rankings.
- ATR family is either implemented with point-in-time coverage or explicitly marked deferred; Sprint 5.1 implements family quality reporting.
- Non-zero cost profile is complete and four-leg cost provenance is stored.
- Extreme-winner contribution semantics are documented in artifact and ADR.
- Artifact Registry and Trading Decision Service remain blocked.

Status:
- Sprint 5.1 completed on 2026-07-01. BUMI and DEWA `reentry_research_v1_1` artifacts were generated from `sl_optimizer_v1_1` sources, episode accounting reconciled, recovery timing is non-null for recovered samples, and all tests passed. Artifact Registry and Trading Decision Service remain blocked.

### Milestone 5.2 — Re-entry Metric Contract Finalization

Purpose:
- Freeze the `reentry_research_v1_1` contract for future Research Artifact Registry work.

Scope:
- Contract-only hardening: unclassified reason accounting, stream-owned metrics, expectancy/CI consistency, ATR family status semantics, validators, and regression tests.
- No new candidate families, optimizer strategy, segmentation, Artifact Registry, or Decision Service.

Acceptance criteria:
- `unclassified_count` equals the sum of `unclassified_reasons`.
- Every stream owns its own expectancy, CI, fold metrics, sample status, quality, and warnings.
- Top-level summary only points to stream status or explicitly labeled aggregates.
- ATR configured candidates are separated from evaluated candidates; coverage `0` yields no best candidate and unusable ATR family.
- Overall `usable_for_reentry_research` depends on valid stream metrics, source validity, metric consistency, and unclassified policy.
- Decision usability remains false.

Status:
- Sprint 5.2 completed on 2026-07-01. `reentry_research_v1_1` contract is finalized for registry preparation with unclassified reason reconciliation, stream-owned metrics, CI sample identity, ATR configured-versus-evaluated semantics, and validator regression coverage. BUMI and DEWA final v1.1 artifacts were regenerated from `sl_optimizer_v1_1` sources and all research tests passed. Artifact Registry and Trading Decision Service remain blocked and uncreated.


### Milestone 6 — Research Artifact Registry and Import

Sprint 6 status: completed on 2026-07-01. Sprint 5.2 is completed and `reentry_research_v1_1` is accepted. Sprint 7 Basic Trading Decision Service remains blocked until explicitly started.

Scope:
- Build a central registry for research artifact discovery, validation, checksum verification, metadata import, lineage, dependency status, latest resolution, staleness, and quarantine metadata.
- Registry stores metadata only; JSON artifact payloads remain on filesystem and are not rewritten.
- No trading actions, public route, dashboard integration, Prediction Engine change, or Decision Service is created.

Architecture:
- Config: `config/trading_research.php` defines allowed roots, supported artifact schemas, path security, checksum, stale thresholds, warning classification, quality grading, unclassified thresholds, and quarantine policy.
- Models: `TradeResearchArtifact` and `TradeResearchArtifactDependency` provide casts, relationships, and query scopes only.
- Services: discovery scans allowed JSON files; validation normalizes heterogeneous artifact schemas; registry imports metadata, resolves dependencies, manages latest flags, and serves internal query methods.
- Commands: `trading-research:import-artifacts` imports metadata with dry-run and JSON output; `trading-research:verify-artifacts` rechecks file integrity, schema, staleness, dependencies, and latest flags.

Database schema:
- `trade_research_artifacts` stores ticker/type/schema, path, checksum, generated/imported timestamps, quality/usability, warnings, summary/source snapshots, logical identity, latest/stale/quarantine flags, and supersession.
- `trade_research_artifact_dependencies` stores artifact, optional resolved artifact, dependency role/type, expected and resolved path/checksum/schema, resolution status, required flag, and metadata.
- Rollback drops dependencies before artifacts. Existing trading, prediction, journal, and decision tables are untouched.

Registry policy:
- Validation status is separate from usage tier and quality grade.
- `latestValid`, `latestResearchUsable`, and `latestDecisionUsable` are distinct and decision resolution never falls back to research-only artifacts.
- Logical identity is based on ticker, artifact type, schema version, generated_at, and generator_version; filename is advisory.
- SHA-256 checksum is deterministic; same checksum import is unchanged, same logical identity with different checksum is conflict.
- Stale and quarantine are registry metadata only; Sprint 6 does not move or delete artifact files.
- Re-entry high unclassified rate is imported as a limitation and can downgrade quality to `limited` without invalidating schema-valid research artifacts.

Acceptance criteria:
- Completed: migrations, models, services, import command, verify command, current artifact import, idempotency check, and tests pass.
- Current BUMI/DEWA artifacts are discovered/imported with dependency rows.
- Import is idempotent and dry-run has no DB writes.
- Invalid/quarantined artifacts do not become latest.
- Latest research works; latest decision returns explicit unavailable/null for non-decision artifacts.
- Existing ResearchArtifactService remains backward compatible.
- PHP and Python research tests pass.

### Milestone 6 — Artifact Registry

Status:
- Blocked until Sprint 5.1 completion.


### Milestone 7 — Basic Trading Decision Service

Sprint 7 status: completed on 2026-07-01. Sprint 6 is completed. Confidence Engine, advanced Reason Engine, Risk Engine, Trade Plan Engine, Dashboard integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Create an in-memory `TradingDecisionService` under `app/Services/Trading/` that converts a normalized prediction snapshot plus Registry evidence into `trading_decision_v1`.
- Use Registry Service dependency injection only; no filesystem scan, Python/FastAPI call, controller integration, route, dashboard card, persistence, notification, or scheduled command.
- Supported Sprint 7 actions are only `WAIT` and `NO_TRADE`; aggressive actions remain unsupported.

Input contract:
- `ticker`, `decision_at`, `prediction`, optional `market_context`, and optional `open_trade`.
- Prediction semantics are normalized into directional or regime categories; `move` is not treated as `up`.
- Probability is validated for range but stored only as evidence.

Output schema:
- `schema_version=trading_decision_v1`, `artifact_type=trading_decision`, action/status, recommendation quality, prediction snapshot, artifact availability, evidence, source artifact metadata, safety gates, structured reasons/warnings/blockers, and metadata.
- `confidence`, `risk`, and `trade_plan` remain null because their engines are blocked.

Safety gates:
1. Input validity
2. Prediction availability
3. Prediction freshness
4. Registry availability
5. Registry integrity
6. Research artifact availability
7. Decision artifact usability
8. Selected-parameter availability
9. Dependency resolution
10. Staleness
11. Quarantine
12. Current implementation capability

Policy:
- Required research artifacts: trade episode dataset, TP optimizer, and SL optimizer.
- Re-entry is optional for generic WAIT/NO_TRADE but is included in evidence and blocks future BUY_BACK only.
- No fallback from decision-usable to research-only candidates.
- Current BUMI/DEWA expected output is safe-downgraded WAIT with decision-usable TP/SL/re-entry unavailable.

Acceptance criteria:
- Completed: Decision service, evidence service, schema validator, Registry integration tests, full PHP tests, and Python research tests pass.
- Current BUMI and DEWA registry state produces WAIT/NO_TRADE only, with confidence/risk/trade_plan null.
- Synthetic decision-ready evidence still does not produce BUY because Sprint 7 action capability is not implemented.
- Registry regression tests, full PHP tests, and Python research tests pass.


### Milestone 7.1 — Decision Contract and Multi-Signal Hardening

Sprint 7.1 status: completed on 2026-07-01. Sprint 7 is completed. Sprint 8 Confidence and Reason Engine remains blocked until explicitly started. Risk Engine, Trade Plan, Dashboard integration, Notification, and Learning remain blocked.

Scope:
- Finalize `trading_decision_v1_1` before Confidence/Reason Engine consumption.
- Support canonical `predictions[]` with backward-compatible single `prediction` input.
- Add semantic roles, prediction identity validation, agreement summary, open-trade scope semantics, readiness model, gate consistency checks, and deterministic decision fingerprint.
- Supported actions remain only WAIT and NO_TRADE; no HOLD, BUY, SELL, CUT_LOSS, BUY_BACK, persistence, route, controller, dashboard, Confidence, Risk, or Trade Plan.

Contract changes:
- Canonical output stores `prediction_snapshots[]`; `prediction_snapshot` remains a deprecated alias for compatibility.
- Decision fields include `decision_scope`, `position_context`, `position_management_status`, `evidence_readiness`, `capability_readiness`, and `action_eligibility`.
- Gate records include `gate`, `evaluated`, `passed`, `severity`, `code`, and `details`; skipped gates use `passed=null`.
- Metadata includes `service_contract_version=basic_decision_v1_1`, fingerprint algorithm, and deterministic SHA-256 fingerprint.

Prediction policy:
- Roles: directional, regime, volatility, unknown.
- Semantics: directional_up, directional_down, directional_neutral, regime_move, regime_no_move, unknown.
- Regime move is not directional up. Contradictory directional predictions produce NO_TRADE. Duplicate prediction identity is rejected. Probability is evidence only.

Scope policy:
- No open trade: entry_evaluation / no_open_trade / not_required.
- Valid open trade: position_management / open_trade / not_implemented with blocker; no implicit HOLD.
- Invalid open trade: NO_TRADE with explicit blocker.

Readiness model:
- Evidence readiness: unavailable, partial, research_ready, decision_ready, invalid.
- Capability readiness: unavailable, partial, basic_only, action_selection_ready.
- Action eligibility: ineligible, blocked, eligible_but_not_supported, eligible.

Acceptance criteria:
- Completed: multiple predictions and legacy single prediction both work.
- Real BUMI/DEWA remain safe WAIT with research_ready/basic_only/blocked.
- Synthetic decision-ready evidence returns unsupported status and never BUY.
- Fingerprint is deterministic and changes when prediction or artifact checksum changes.
- Full PHP and Python regression tests pass.

### Milestone 7 — Trading Decision Service

Status:
- Blocked until research artifacts become registry-ready and decision-grade policy is accepted.

### Milestone 5 — Trading Decision Service

Purpose:
- Produce initial trading action from prediction and research evidence.

Output:
- Decision JSON with action, confidence placeholder, trade plan placeholder, and reasons placeholder.

Dependencies:
- Milestone 1.
- Existing prediction flow.

Files created:
- `app/Services/Trading/TradingDecisionService.php`
- `tests/Unit/TradingDecisionServiceTest.php`

Files changed:
- Optional integration in `PredictionController` after service is stable.

Acceptance criteria:
- Missing research artifact prevents aggressive `BUY`.
- Prediction `up` plus positive research can produce `BUY` or `ACCUMULATE`.
- Open trade state can produce `HOLD`.

Risk:
- Accidentally encoding static thresholds.

Complexity:
- Medium.

### Milestone 5 — Confidence Engine

Purpose:
- Create explainable multi-component confidence.

Output:
- Component scores for prediction, expectancy, stability, trend, momentum, volume, support/resistance, sentiment, market regime, and volatility.

Dependencies:
- Milestone 4.

Files created:
- `app/Services/Trading/ConfidenceEngineService.php`

Acceptance criteria:
- Confidence breakdown sums or aggregates deterministically.
- Each component includes source and explanation.
- Missing components reduce confidence transparently.

Risk:
- Treating raw model probability as final confidence.

Complexity:
- Medium.

### Milestone 6 — Reason Engine

Purpose:
- Generate structured explanations.

Output:
- At least 10 reason candidates when data is available.

Dependencies:
- Milestone 4 and 5.

Files created:
- `app/Services/Trading/ReasonEngineService.php`

Acceptance criteria:
- Reasons include category, evidence, impact, and source.
- No generic filler reason without evidence.

Risk:
- Black-box text that cannot be audited.

Complexity:
- Medium.

### Milestone 7 — Risk Engine

Purpose:
- Calculate risk/reward, expected drawdown, SL probability, optional Kelly fraction, and position size recommendation.

Output:
- Risk payload in decision JSON.

Dependencies:
- TP/SL artifact availability.

Files created:
- `app/Services/Trading/RiskEngineService.php`

Acceptance criteria:
- Position size is capped for volatile stocks.
- Risk category is explainable.

Risk:
- Overaggressive sizing.

Complexity:
- Medium.


### Milestone 8 — Confidence and Reason Engine

Sprint 8 status: prototype completed on 2026-07-01. Sprint 7.1 is completed. Risk Engine, Trade Plan Engine, Advanced Action Selection, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add `ConfidenceEngineService` and `ReasonEngineService` under `app/Services/Trading/`.
- Evolve decision schema to `trading_decision_v1_2` and service contract to `basic_decision_v1_2`.
- Confidence separates prediction probability, evidence confidence, and action confidence.
- Reason Engine produces deterministic structured reasons; no LLM, network, Python, FastAPI, route, controller, persistence, Risk Engine, or Trade Plan.
- Actions remain WAIT and NO_TRADE only.

Confidence policy:
- Internal schema `trading_confidence_v1`.
- Components are weighted from `config/trading_confidence.php`.
- Caps and penalties are configured and explainable.
- Probability magnitude is evidence only and does not increase confidence without calibration.
- Current BUMI/DEWA: evidence confidence available, action confidence null.

Reason policy:
- Internal schema `trading_reason_v1`.
- Reasons include code, category, severity, polarity, impact, deterministic message, source metadata, evidence, and rank.
- Warnings and blockers derive from structured reasons.
- Ordering: critical, blocking, warning, supportive, informational; then category/code order.

Acceptance criteria:
- Completed: Confidence/Reason services created and integrated into TradingDecisionService with PHP and Python tests passing.
- Prototype note: Sprint 8 synthetic decision-ready fixture allowed action confidence, but Sprint 8.1 supersedes this with action-specific trade-action confidence unavailable until an action candidate exists.
- Fingerprint includes confidence and reason results.
- Full PHP and Python regression tests pass.


### Milestone 8.1 — Confidence Scope and Reason Prioritization Hardening

Sprint 8.1 status: completed on 2026-07-01. Sprint 8 is prototype completed. Sprint 9 Risk and Trade Plan Contract Foundation is blocked. Advanced Action Selection, Dashboard, Notification, and Learning remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_3` and confidence schema to `trading_confidence_v1_1`.
- Split confidence into evidence, safety-decision, and trade-action scopes.
- Require action identity before trade-action confidence can be populated.
- Remove implementation capability from weighted evidence components and move capability into readiness/eligibility metadata.
- Add explicit calculation stages, missing-component policy, confidence interpretation, reason primary/supporting/diagnostic grouping, source aggregation, and dominant blocker priority.
- Actions remain only WAIT and NO_TRADE. Risk, Trade Plan, Action Selection, Dashboard, Notification, and Learning remain blocked.

Acceptance criteria:
- Completed: synthetic decision-ready evidence does not populate trade-action confidence without action candidate.
- Completed: safety confidence is available for WAIT/NO_TRADE.
- Completed: compatibility warnings/blockers derive from canonical reasons.
- Completed: fingerprint includes updated confidence scopes and reason classification.
- Completed: full PHP and Python tests pass.

### Milestone 9 — Risk and Trade Plan Contract Foundation

Sprint 9 status: completed on 2026-07-01. Sprint 8.1 is completed. Action Selection Engine, Position Sizing Engine, Position Management Engine, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_4` and service contract to `basic_decision_v1_4`.
- Add `RiskEngineService` with schema `trading_risk_v1` and separate research-risk evidence from action-specific decision risk.
- Add `TradePlanService` with schema `trading_trade_plan_v1` and explicit unavailable plan sections.
- Keep supported actions limited to `WAIT` and `NO_TRADE`; no BUY, HOLD, SELL, CUT_LOSS, BUY_BACK, position sizing, routes, controllers, persistence, or production integration.
- Preserve no-fallback policy: research-only TP/SL/re-entry candidates are not promoted to selected production parameters.

Risk policy:
- Research-risk evidence may use normalized Registry metadata only.
- Decision risk requires action candidate identity, selected TP/SL, decision-usable artifacts, fresh non-quarantined sources, resolved dependencies, and calculation capability.
- Without decision risk eligibility, all decision-risk numeric metrics remain null.
- Position sizing is `not_implemented` with null size outputs.

Trade-plan policy:
- Trade plan is unavailable without action candidate, decision risk, selected entry/TP/SL, action support, and valid decision-usable sources.
- Current BUMI/DEWA expose structured unavailable plan objects, not executable plans.
- Open-trade context does not imply HOLD/SELL/CUT_LOSS and does not reuse current stop/target as generated plan.

Acceptance criteria:
- Completed: Risk and Trade Plan services are created and integrated through `TradingDecisionService`.
- Completed: BUMI/DEWA risk and trade plan objects are structured but decision risk and executable plan remain unavailable.
- Completed: no numeric production TP/SL/RR/position size is emitted when unavailable.
- Completed: Reason Engine receives risk/trade-plan status and compatibility fields derive from canonical reasons.
- Completed: fingerprint includes risk and trade-plan schema/status/reason codes.
- Completed: full PHP and Python regression tests pass.

### Milestone 10 — Action Candidate and Eligibility Contract Foundation

Sprint 10 status: Action Candidate Foundation completed on 2026-07-01. Sprint 9 is completed. Final Action Promotion, Position Sizing Engine, Position Management Engine, Executable Risk and Trade Plan, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_5` and service contract to `basic_decision_v1_5`.
- Add `ActionCandidateService` with schema `trading_action_candidate_v1` for non-executable candidate hypotheses.
- Separate action candidate, candidate eligibility, final action, and promotion status.
- Keep final supported actions limited to WAIT and NO_TRADE.
- Provide candidate identity to Risk and Trade Plan contracts without creating Action Promotion, Position Sizing, Position Management, routes, controllers, persistence, or production integration.

Candidate policy:
- Long-entry candidate requires directional-up prediction, fresh non-conflicting prediction evidence, decision-ready evidence, decision-usable TP/SL, selected TP/SL, resolved dependencies, fresh artifacts, and non-quarantined sources.
- Regime evidence may support but never replaces directional prediction.
- Research-only artifacts, evidence-confidence score, and probability magnitude cannot create candidate-ready output.
- Candidate is always `non_executable`; promotion remains `not_implemented`.

Acceptance criteria:
- Completed: candidate object and promotion object are structured in decision output.
- Completed: current BUMI/DEWA do not produce candidate-ready output.
- Completed: synthetic decision-ready directional-up evidence can produce candidate-ready but final action remains WAIT.
- Completed: Risk Engine receives candidate identity; Trade Plan remains unavailable without decision risk.
- Completed: full PHP and Python regression tests pass.

### Milestone 10.1 — Action Selection and Promotion Contract Hardening

Sprint 10.1 status: completed on 2026-07-01. Sprint 10 Action Candidate Foundation is completed. Action-Specific Risk Evaluation, Executable Trade Plan, Position Sizing, Position Management, Dashboard, Notification, and Learning remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_6` and service contract to `basic_decision_v1_6`.
- Add `ActionSelectionService` with schema `trading_action_selection_v1`.
- Add `ActionPromotionService` with schema `trading_action_promotion_v1`.
- Separate candidate formation, selection, promotion, execution readiness, and safety action.
- Keep final top-level actions limited to WAIT and NO_TRADE.

Selection policy:
- Selection validates candidate availability, schema, identity, ticker/scope/position consistency, evidence readiness, trade-action confidence identity, decision-risk identity, trade-plan identity, capability, blockers, and selection policy availability.
- Sprint 10.1 has no production selection policy; selected candidate remains null.
- No probability, confidence, RR, TP/SL, expectancy, or research fallback threshold may select a candidate.

Promotion policy:
- Promotion requires selected candidate, capability, risk, trade plan, safety policy, and no blockers.
- Sprint 10.1 promotion is contract-only; promoted action and executable action remain null.
- Top-level `action` equals explicit safety action while promoted action is null.

Acceptance criteria:
- Completed: Action Selection and Action Promotion services are created and integrated.
- Completed: real BUMI/DEWA selected candidate remains null and safety action remains WAIT.
- Completed: synthetic candidate-ready is not selected without confidence/risk/plan readiness.
- Completed: synthetic contract-ready is not promoted because capability is disabled.
- Completed: fingerprint includes selection and promotion schema/status/eligibility.
- Completed: full PHP and Python regression tests pass.

### Milestone 11 — Action-Specific Risk Evaluation Foundation

Sprint 11 status: completed on 2026-07-01. Sprint 10.1 is completed. Trade Plan Parameter Materialization, Position Sizing, Position Management, Final Action Promotion Policy, Dashboard, Notification, and Learning remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_7`, service contract to `basic_decision_v1_7`, and risk schema to `trading_risk_v1_1`.
- Add `ActionRiskEvaluationService` with schema `trading_action_risk_v1`.
- Make `action_specific_risk` the canonical candidate-risk source inside Risk Engine.
- Accept only normalized selected-parameter evidence; no filesystem, JSON payload, or research-only fallback.
- Compute only gross long-entry percentage geometry when candidate and selected TP/SL evidence are decision-grade.

Risk policy:
- Real BUMI/DEWA remain action-risk unavailable because selected decision-grade TP/SL values are unavailable.
- Synthetic tests may provide `trading_selected_parameters_v1` evidence to validate gross geometry.
- Probabilistic, expected value, net, capital, portfolio, execution, position sizing, and position-management risk remain unavailable/not implemented.
- Gross RR is a metric only and must not select or promote a candidate.

Acceptance criteria:
- Completed: ActionRiskEvaluationService is created and integrated through RiskEngineService.
- Completed: synthetic decision-grade percentage parameters can produce deterministic gross geometry.
- Completed: real BUMI/DEWA action risk remains unavailable with all numeric production metrics null.
- Completed: trade plan, selection, promotion, final action, and position sizing remain blocked/unavailable.
- Completed: full PHP and Python regression tests pass.

### Milestone 12 — Trade Plan Parameter Materialization Foundation

Sprint 12 status: completed on 2026-07-01. Sprint 11 is completed. Position Sizing, Position Management, Execution Planning, Final Action Promotion Policy, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Evolve decision schema to `trading_decision_v1_8`, service contract to `basic_decision_v1_8`, and trade-plan schema to `trading_trade_plan_v1_1`.
- Add `TradePlanMaterializationService` with `trading_reference_trade_plan_v1` and `trading_entry_reference_v1` contracts.
- Build non-executable reference plans only from candidate-ready, selected decision-grade parameters, evaluated action risk, and explicit entry-reference evidence.
- Keep selection, promotion, executable action, position sizing, and position management blocked.

Policy:
- Real BUMI/DEWA remain trade-plan unavailable because candidate/selected-parameter/action-risk prerequisites are unavailable.
- Synthetic parameters without entry reference can produce `parameter_ready` reference plan.
- Synthetic valid entry reference can produce materialized reference plan, still non-executable.
- Trade plan uses Action Risk as canonical geometry source and must not recalculate divergent risk.

Acceptance criteria:
- TradePlanMaterializationService is created and integrated through TradePlanService.
- Reference plan is candidate-specific, provenance-backed, deterministic, and non-executable.
- No research fallback, holding materialization, re-entry materialization, position sizing, position management, order payload, selection, or promotion is created.
- Completed: Full PHP and Python regression tests pass before Sprint 12 is marked completed.

### Milestone 13 — Capital Risk and Position Sizing Contract Foundation

Sprint 13 status: completed on 2026-07-01. Sprint 12 is completed. Position Management, Execution Planning, Final Action Promotion Policy, Portfolio Risk, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit `trading_capital_context_v1` and `trading_capital_risk_policy_v1` input contracts.
- Add `trading_capital_risk_v1` as gross single-candidate reference capital-risk evaluation.
- Add `trading_position_sizing_v1` as non-executable reference sizing.
- Evolve decision schema to `trading_decision_v1_9`, service contract to `basic_decision_v1_9`, and risk schema to `trading_risk_v1_2`.
- Preserve trade-plan schema `trading_trade_plan_v1_1` with compatible sizing summary only.

Boundaries:
- Capital context and risk policy must be explicit inputs; no default capital, default risk percentage, account balance lookup, or Trade Journal fallback.
- Canonical loss source is `risk.action_specific_risk.metrics.gross_loss_per_unit`.
- Position sizing computes reference units only; executable quantity remains null.
- Confidence, prediction probability, quality grade, and gross RR must not alter sizing.
- Net risk, portfolio risk, lot policy, liquidity, cash validation, execution costs, position management, and execution planning remain deferred.

Acceptance criteria:
- CapitalRiskEvaluationService and PositionSizingService exist.
- Real BUMI/DEWA capital risk and sizing remain unavailable.
- Synthetic explicit capital context and risk policy produce maximum loss amount and reference units.
- Reference sizing is non-executable; selected candidate, promoted action, and executable action remain null.
- Completed: Full PHP and Python regression tests pass before Sprint 13 is marked completed.

### Milestone 14 — Execution Readiness and Market Constraint Contract Foundation

Sprint 14 status: completed on 2026-07-01. Sprint 13 ADR closeout is validated. Portfolio Risk, Position Management, Final Action Promotion Policy, Broker Execution, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit market-constraint, execution-cash, execution-cost, and liquidity evidence contracts.
- Add `trading_execution_constraints_v1` for reference-only constraint adjustment.
- Add `trading_execution_readiness_v1` to classify unavailable, partial, or reference-ready execution evidence.
- Evolve decision schema to `trading_decision_v1_10`, service contract to `basic_decision_v1_10`, and trade-plan schema to `trading_trade_plan_v1_2`.

Boundaries:
- No default unit step, minimum order, tick size, fees, slippage, available cash, liquidity, or broker settings.
- Constraint-adjusted reference units are not executable quantity.
- Missing cost or liquidity evidence does not imply zero costs or unlimited liquidity.
- Portfolio risk, position management, broker execution, selection policy, and promotion policy remain blocked.

Acceptance criteria:
- ExecutionConstraintEvaluationService and ExecutionReadinessService exist.
- Real BUMI/DEWA execution readiness remains unavailable.
- Synthetic explicit constraints can align units, cash-cap units, and reconcile gross risk.
- Reference-ready never becomes executable; executable quantity, selected candidate, promoted action, and executable action remain null.
- Completed: Full PHP and Python regression tests pass before Sprint 14 is marked completed.

### Milestone 15 — Portfolio Risk and Exposure Contract Foundation

Sprint 15 status: completed on 2026-07-02. Sprint 14 is completed. Position Management, Broker Execution, Final Action Promotion Policy, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit portfolio context and explicit position snapshot contracts.
- Add exposure aggregation contract for reference gross notional, explicit capital at risk, ticker exposure, and optional sector exposure.
- Add portfolio risk policy and post-candidate portfolio-risk evaluation.
- Evolve decision schema to `trading_decision_v1_11`, service contract to `basic_decision_v1_11`, and risk schema to `trading_risk_v1_3`.

Boundaries:
- No Trade Journal, database, dashboard, hidden market, or empty-portfolio fallback.
- No portfolio optimization, correlation model, approval, position management, selection, promotion, or broker execution.
- Portfolio evaluation is reference-only and keeps `approved=false`.

Acceptance criteria:
- ExposureAggregationService and PortfolioRiskEvaluationService exist.
- Real BUMI/DEWA portfolio risk remains unavailable.
- Synthetic exposure aggregation and post-candidate policy checks are deterministic.
- Limit exceeded blocks selection without creating SELL/CUT_LOSS/BUY.
- Completed: Full PHP and Python regression tests pass before Sprint 15 is marked completed.

### Milestone 16 — Position Management State Contract Foundation

Sprint 16 status: completed on 2026-07-02. Sprint 15 is completed. Position Management Action Selection, Portfolio Approval, Final Action Promotion Policy, Broker Execution, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit managed-position and market-observation contracts.
- Add reference-only position-state evaluation for gross unrealized PnL, holding duration, stop breach, and target reach.
- Add position-management monitoring contract while keeping management actions and executable instructions null.
- Evolve decision schema to `trading_decision_v1_12` and service contract to `basic_decision_v1_12`.

Boundaries:
- No Trade Journal/database fallback and no synthetic open-position assumption.
- Stop/target conditions are observations, not HOLD/SELL/CUT_LOSS actions.
- Position management action selection, promotion, and execution remain blocked.

Acceptance criteria:
- PositionStateEvaluationService and PositionManagementService exist.
- No-position flow remains not required.
- Explicit open-position monitoring computes deterministic PnL and conditions.
- No HOLD, SELL, CUT_LOSS, management action, or executable instruction is produced.
- Completed: Full PHP and Python regression tests pass before Sprint 16 is marked completed.

### Milestone 16.1 — Position Management Policy, Candidate, and Selection Contract Foundation

Sprint 16.1 status: completed on 2026-07-02. Sprint 16 is completed. Portfolio Approval, Entry Final Action Promotion Policy, Position Management Promotion, Position Management Execution, Broker Execution, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit reference-only position-management policy contract.
- Add condition-to-review-candidate boundary for stop breach, target reach, missing protection, and stale observation.
- Add deterministic management candidate identity tied to position state, observation, policy, and rule.
- Add management selection contract with risk, plan, portfolio approval, promotion, and execution unavailable.
- Evolve decision schema to `trading_decision_v1_14`, service contract to `basic_decision_v1_14`, and position-management schema to `trading_position_management_v1_1`.

Boundaries:
- No default management policy and no implicit HOLD when no condition exists.
- Stop breach and target reach may only form review hypotheses through explicit policy; they do not promote to CUT_LOSS or SELL.
- Entry candidate/selection flow remains separate from management candidate/selection flow.

Acceptance criteria:
- PositionManagementPolicyService, PositionManagementCandidateService, and PositionManagementSelectionService exist.
- Real flow without explicit policy produces candidate unavailable and safety WAIT.
- Synthetic explicit policy can produce deterministic review candidates while selected/promoted/executable fields remain null.
- Management risk, management plan, portfolio approval, management promotion, and execution remain not implemented.
- Completed: Full PHP and Python regression tests pass before Sprint 16.1 is marked completed.

### Milestone 17 — Portfolio Approval and Authorization Contract Foundation

Sprint 17 status: completed on 2026-07-02. Sprint 16.1 is completed. Management Risk, Management Plan, Entry Final Selection Policy, Entry Action Promotion, Management Promotion, Broker Execution, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add explicit portfolio-approval policy contract and prerequisite evidence checks.
- Add explicit reference authorization evidence validation bound to portfolio, candidate, policy, scope, issuer, expiry, and approval-context fingerprint.
- Add portfolio approval contract that separates eligible reference approval, approved reference, production approval, and execution authorization.
- Evolve decision schema to `trading_decision_v1_14` and service contract to `basic_decision_v1_14` while keeping risk schema `trading_risk_v1_3`.

Boundaries:
- Portfolio risk checks passed do not imply approval.
- Reference approval does not imply production approval or execution authorization.
- Entry portfolio approval does not apply to position-management review candidates.
- No default policy, default authorization, auto-approval, order payload, route, controller, persistence, or broker integration.

Acceptance criteria:
- PortfolioApprovalPolicyService, PortfolioAuthorizationService, and PortfolioApprovalService exist.
- All checks passed without explicit authorization remains eligible but not approved.
- Valid synthetic reference authorization can produce `approved_reference` while production/execution approval remain false.
- Limit-exceeded portfolio risk cannot be overridden by authorization.
- Final action remains WAIT/NO_TRADE and selected/promoted/executable fields remain null.
- Completed: Full PHP and Python regression tests pass before Sprint 17 is marked completed.

### Milestone 18 — Position Management Risk and Review Plan Contract Foundation

Sprint 18 status: completed on 2026-07-02. Sprint 17 is completed. Management Portfolio Approval, Management Production Approval, Management Action Promotion, Entry Final Selection Policy, Entry Action Promotion, Execution Authorization, Broker Execution, Dashboard Integration, Notification Engine, and Learning Engine remain blocked.

Scope:
- Add management-specific risk context for explicit position-management review candidates.
- Use Position State as canonical source for PnL, holding duration, and stop/target condition facts.
- Add non-executable management review plan that records required and unavailable evidence without generating actions, quantities, exits, or stop/target updates.
- Evolve decision schema to `trading_decision_v1_15`, service contract to `basic_decision_v1_15`, and position-management schema to `trading_position_management_v1_2`.

Boundaries:
- Management risk evaluated does not mean a management action is selected.
- Review plan ready does not mean action plan ready.
- Stop breach observed does not imply CUT_LOSS, SELL, HOLD, or executable instruction.
- Entry services and entry portfolio approval remain separate from management risk/review contracts.

Acceptance criteria:
- PositionManagementRiskEvaluationService and PositionManagementReviewPlanService exist.
- Stop-breach and target-reach reference metrics are deterministic and non-executable.
- Missing protection creates no default stop and stale observation fetches no market data.
- Management action plan, management portfolio approval, execution authorization, promotion, and broker execution remain not implemented.
- Full PHP and Python regression tests pass before Sprint 18 is marked completed.

### Milestone 8 — Trade Plan Engine

Purpose:
- Convert research parameters into entry, TP, SL, trailing stop, re-entry, exit, and invalidation plan.

Output:
- `trade_plan` object in decision JSON.

Dependencies:
- Milestone 4 and 7.

Files created:
- `app/Services/Trading/TradePlanService.php`

Acceptance criteria:
- TP/SL comes from artifacts, not hardcoded defaults.
- If artifact is unavailable, output must say plan unavailable.

Risk:
- Static TP/SL sneaking in as defaults.

Complexity:
- Medium.

### Milestone 9 — Decision Dashboard

Purpose:
- Display decisions and evidence.

Output:
- New route and Blade view for trading decisions.

Dependencies:
- Milestone 4 to 8.

Files created:
- `app/Http/Controllers/TradingDecisionController.php`
- `resources/views/trading-decisions/index.blade.php`

Acceptance criteria:
- Shows action, confidence, plan, risk, reasons, research evidence.
- Does not replace existing prediction dashboard.

Risk:
- UI overstating decision as investment advice.

Complexity:
- Medium.

### Milestone 10 — Notification Engine

Purpose:
- Trigger alerts from decision and price state.

Output:
- Alert table, alert service, dispatch command.

Dependencies:
- Milestone 8 and 9.

Files created:
- Migration for `trading_alerts`.
- `app/Services/Trading/NotificationSignalService.php`
- `app/Console/Commands/DispatchTradingAlertsCommand.php`

Acceptance criteria:
- Alerts generated for TP, SL, entry zone, re-entry zone, breakout, breakdown.
- Duplicate alerts are suppressed.

Risk:
- Alert spam.

Complexity:
- Medium.

### Milestone 11 — Outcome Learning

Purpose:
- Evaluate decisions and completed trades.

Output:
- Outcome records and reports.

Dependencies:
- Trade decisions and alerts.

Files created:
- Migration for `trading_decision_outcomes`.
- `app/Services/Trading/OutcomeLearningService.php`

Acceptance criteria:
- Records whether TP/SL/holding/re-entry was correct.
- Produces improvement recommendations.

Risk:
- Learning from too-small sample size.

Complexity:
- High.

### Milestone 12 — Adaptive Weight Calibration

Purpose:
- Adjust confidence weights from historical outcome evidence.

Output:
- Calibration artifacts.

Dependencies:
- Milestone 11.

Files created:
- `quant/trading_decision/calibrate_confidence_weights.py`
- `app/Services/Trading/CalibrationArtifactService.php`

Acceptance criteria:
- Weights are versioned and bounded.
- Calibration can be rolled back.

Risk:
- Overfitting confidence to recent trades.

Complexity:
- High.

### Milestone 13 — Portfolio Ranking

Purpose:
- Rank multiple stocks by risk-adjusted decision attractiveness.

Output:
- Portfolio ranking endpoint and dashboard panel.

Dependencies:
- Milestone 4 to 8.

Files created:
- `app/Services/Trading/PortfolioRankingService.php`

Acceptance criteria:
- Ranking uses expected return, risk, confidence, expectancy, and stability.
- Supports BUMI/DEWA first, then expands later.

Risk:
- Comparing stocks with incompatible research coverage.

Complexity:
- Medium.

### Milestone 14 — Stock Personality

Purpose:
- Model ticker-specific behavior such as volatility, stale price tendency, pullback depth, recovery speed, and sentiment coverage.

Output:
- Stock personality artifact used by decision and confidence engines.

Dependencies:
- Walk-forward and outcome learning artifacts.

Files created:
- `quant/trading_research/stock_personality.py`

Acceptance criteria:
- Personality values are derived from historical data.
- Decision engine can explain stock-specific adjustment.

Risk:
- Personality artifact used as static bias without validation.

Complexity:
- High.

## 5. Sprint Plan

### Sprint 1 — Artifact Foundation

Scope:
- Research artifact folder.
- Artifact schema convention.
- `ResearchArtifactService`.
- Unit tests.
- Example artifacts.

Independent outcome:
- Laravel can load and validate example artifacts without dashboard, notification, learning, or confidence engine.

### Sprint 2 — Walk-forward Event Dataset Prototype

Scope:
- Python prototype for event dataset from BUMI/DEWA datasets.
- Calculate return horizons, MFE, MAE, drawdown.

Independent outcome:
- CSV and JSON summary generated under `output/trading_research/`.

### Sprint 3 — TP/SL Research Prototype

Scope:
- TP candidates 5/10/15/20/25/30.
- SL candidates fixed, ATR, swing low, support, trailing ATR.

Independent outcome:
- Optimizer artifact can be read by `ResearchArtifactService`.

### Sprint 4 — Re-entry Research Prototype

Scope:
- Pullback after TP.
- Recovery duration.
- WAIT/ACCUMULATION/BUY_BACK zones.

Independent outcome:
- Re-entry artifact available per ticker.

### Sprint 5 — Basic Decision Service

Scope:
- Combine prediction + artifact availability.
- Produce safe actions: `BUY`, `ACCUMULATE`, `WAIT`, `NO_TRADE`.

Independent outcome:
- Decision JSON fixture generated in tests.

### Sprint 6 — Confidence and Reason Engines

Scope:
- Component confidence.
- Structured reasons.

Independent outcome:
- Decision output includes auditable breakdown and reasons.

### Sprint 7 — Risk and Trade Plan Engines

Scope:
- RR, expected drawdown, position sizing, entry, TP, SL, holding, invalidation.

Independent outcome:
- Decision output becomes complete trade plan.

### Sprint 8 — Dashboard Integration

Scope:
- New dashboard route and Blade page.

Independent outcome:
- User can inspect decision and evidence.

### Sprint 9 — Notification Foundation

Scope:
- Alert table, alert service, dispatch command.

Independent outcome:
- Pending alerts can be generated from decisions.

### Sprint 10 — Outcome Learning

Scope:
- Evaluate decision outcomes.

Independent outcome:
- Closed decision records produce learning report.

### Sprint 11 — Calibration and Portfolio Ranking

Scope:
- Adaptive weights.
- Multi-stock ranking.

Independent outcome:
- Portfolio ranking uses calibrated decision evidence.

## 6. Folder Structure

### Laravel

```text
app/
  Services/
    Research/
      ResearchArtifactService.php
    Trading/
      TradingDecisionService.php
      ActionSelectionService.php
      ConfidenceEngineService.php
      ReasonEngineService.php
      RiskEngineService.php
      TradePlanService.php
      NotificationSignalService.php
      PortfolioRankingService.php
      OutcomeLearningService.php
  Http/
    Controllers/
      TradingDecisionController.php
  Models/
    TradingDecision.php
    TradingAlert.php
    TradeResearchArtifact.php
    TradingDecisionOutcome.php
  Console/
    Commands/
      ImportTradingResearchArtifactsCommand.php
      DispatchTradingAlertsCommand.php
      EvaluateTradingDecisionOutcomesCommand.php
```

### Python

```text
quant/
  trading_research/
    walk_forward_trade_research.py
    event_dataset_builder.py
    excursion_metrics.py
    tp_optimizer.py
    stop_loss_optimizer.py
    reentry_research.py
    stock_personality.py
    artifact_schema.py
  trading_decision/
    calibrate_confidence_weights.py
    validate_decision_outputs.py
```

### Storage and Artifacts

```text
storage/app/trading_research/
  examples/
  registry/
  latest/

output/trading_research/
  events/
  summaries/
  reports/
  calibration/
```

### Dashboard

```text
resources/views/trading-decisions/
  index.blade.php
  show.blade.php
  components/
```

### Notification

```text
app/Notifications/
  TradingAlertNotification.php
```

## 7. Database Evolution

### 7.1 `trade_research_artifacts`

Needed because Laravel must know which artifact is current and valid.

Relations:
- Belongs to ticker symbol logically.
- Referenced by decisions through `research_snapshot` or artifact IDs.

Key columns:
- `id`
- `ticker`
- `artifact_type`
- `schema_version`
- `artifact_path`
- `generated_at`
- `summary`
- `status`

### 7.2 `trading_decisions`

Needed to persist each decision snapshot and support auditability.

Relations:
- Belongs to `stock`.
- May reference open `trade`.
- Has many `trading_alerts`.
- Has one or many outcome evaluations.

Key columns:
- `stock_id`
- `trade_id`
- `decision_date`
- `action`
- `confidence`
- `recommendation_quality`
- `risk_level`
- `entry_zone_low`
- `entry_zone_high`
- `take_profit`
- `stop_loss`
- `expected_return`
- `expected_drawdown`
- `expected_holding_days`
- `probability_tp_hit`
- `probability_sl_hit`
- `risk_reward`
- `historical_expectancy`
- `model_snapshot`
- `research_snapshot`
- `confidence_breakdown`
- `reasons`
- `trade_plan`

### 7.3 `trading_alerts`

Needed for notification lifecycle.

Relations:
- Belongs to `trading_decision`.
- Belongs to `stock`.

Key columns:
- `alert_type`
- `trigger_price`
- `status`
- `sent_at`
- `payload`

### 7.4 `trading_decision_outcomes`

Needed for learning engine.

Relations:
- Belongs to `trading_decision`.
- Optional link to `trade`.

Key columns:
- `outcome_type`
- `realized_return`
- `realized_drawdown`
- `actual_holding_days`
- `tp_hit`
- `sl_hit`
- `exit_quality`
- `failed_components`
- `learning_notes`

## 8. JSON Schema

Every JSON artifact must include:
- `schema_version`
- `artifact_type`
- `ticker` or `scope.tickers`
- `generated_at`
- `source`
- `data`
- `quality`
- `notes`

### 8.1 Walk-forward Schema

```json
{
  "schema_version": "walk_forward_v1",
  "artifact_type": "walk_forward",
  "ticker": "BUMI",
  "generated_at": "2026-07-01T00:00:00+07:00",
  "folds": [],
  "summary": {
    "event_count": 0,
    "return_horizons": {},
    "mfe": {},
    "mae": {},
    "drawdown": {},
    "fold_stability": null
  },
  "quality": {
    "status": "example",
    "sample_size": 0,
    "warnings": []
  }
}
```

### 8.2 TP Optimizer Schema

```json
{
  "schema_version": "tp_optimizer_v1",
  "artifact_type": "tp_optimizer",
  "ticker": "BUMI",
  "generated_at": "2026-07-01T00:00:00+07:00",
  "candidates": [],
  "selected": {
    "tp_pct": null,
    "expectancy": null,
    "hit_rate": null,
    "average_holding_days": null
  },
  "quality": {
    "status": "example",
    "warnings": []
  }
}
```

### 8.3 Re-entry Schema

```json
{
  "schema_version": "reentry_v1",
  "artifact_type": "reentry",
  "ticker": "BUMI",
  "generated_at": "2026-07-01T00:00:00+07:00",
  "zones": {
    "wait": {},
    "accumulation": {},
    "buy_back": {}
  },
  "recovery": {},
  "quality": {
    "status": "example",
    "warnings": []
  }
}
```

### 8.4 Decision Schema

```json
{
  "schema_version": "trading_decision_v1",
  "artifact_type": "decision",
  "ticker": "BUMI",
  "decision_date": "2026-07-01",
  "action": "WAIT",
  "confidence": 0,
  "recommendation_quality": "N/A",
  "risk_level": "unknown",
  "entry_zone": {},
  "take_profit": {},
  "stop_loss": {},
  "expected": {},
  "confidence_breakdown": {},
  "trade_plan": {},
  "reasons": [],
  "warnings": [],
  "source_artifacts": {}
}
```

### 8.5 Notification Schema

```json
{
  "schema_version": "trading_notification_v1",
  "artifact_type": "notification",
  "ticker": "BUMI",
  "alert_type": "entry_zone",
  "trigger": {},
  "payload": {},
  "status": "pending"
}
```

### 8.6 Learning Schema

```json
{
  "schema_version": "trading_learning_v1",
  "artifact_type": "learning",
  "ticker": "BUMI",
  "decision_id": null,
  "outcome": {},
  "component_evaluation": {},
  "recommendations": []
}
```

## 9. Coding Standard

Rules:
- Do not modify the stable Prediction Engine unless explicitly required.
- New trading features must live in Research or Trading layers.
- No static TP/SL/holding thresholds as production defaults.
- All trading parameters must come from versioned artifacts or be explicitly marked unavailable.
- Every JSON artifact must have `schema_version` and `artifact_type`.
- Service classes must have single responsibility.
- Do not duplicate model prediction calls across services; use a single integration boundary.
- No black-box decision output; every decision needs reasons and evidence references.
- Unit tests are required for every new service.
- External API/network calls must not be required for unit tests.
- Missing artifact must degrade safely to `WAIT` or `NO_TRADE`.
- Stale artifact must reduce confidence and emit warning.
- DB migrations must be additive and reversible.
- Dashboard must display risk and limitations clearly.
- All generated artifacts must be deterministic for identical inputs.

## 10. Development Rules

1. This roadmap is the source of truth.
2. Before implementing a milestone, confirm its scope in this document.
3. If architecture changes, update this roadmap first.
4. Only after roadmap update may code change.
5. Keep commits small and modular.
6. Do not mix dashboard, notification, learning, and prediction changes in one sprint.
7. Sprint 1 is limited to artifact folder, schema convention, artifact reader service, unit tests, and example artifacts.
8. Later sprints must not bypass artifact validation.
9. Prediction outputs are inputs to decision, not replacements for research evidence.
10. The system is Decision Support, not an investment recommendation engine.

## 11. Progress Log

### 2026-07-01 — Sprint 1 Completed

Planned:
- Create roadmap.
- Create research artifact examples.
- Create `ResearchArtifactService`.
- Create unit tests.

Completed:
- Created `docs/ROADMAP_AI_TRADING.md` as the implementation source of truth.
- Created example artifacts under `storage/app/trading_research/examples/`.
- Created `app/Services/Research/ResearchArtifactService.php`.
- Created `tests/Unit/ResearchArtifactServiceTest.php`.
- Verified Sprint 1 with `php artisan test tests/Unit/ResearchArtifactServiceTest.php` — 5 tests passed.
