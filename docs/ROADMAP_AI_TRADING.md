# AI Trading Decision Support Roadmap

Last updated: 2026-07-01
Status: Sprint 1 completed
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
- Artifacts under `output/trading_research/`.

Dependencies:
- Milestone 1 schema.
- Existing OHLCV and prediction research datasets.

Files created:
- `quant/trading_research/walk_forward_trade_research.py`
- `quant/trading_research/event_dataset_builder.py`
- `quant/trading_research/artifact_schema.py`

Files changed:
- Optional Artisan command in later milestone.

Acceptance criteria:
- Expanding-window folds only.
- No random train/test split.
- Output includes return 1/3/5/10/20/30, MFE, MAE, drawdown, TP hit stats, and fold summary.

Risk:
- Look-ahead bias if event features use future data.

Complexity:
- Medium.

### Milestone 3 — Artifact Import and Registry

Purpose:
- Register generated artifacts so Laravel can find the latest valid evidence.

Output:
- Artifact registry table or JSON index.
- Import command.

Dependencies:
- Milestone 1 and 2.

Files created:
- Migration for `trade_research_artifacts`.
- `app/Console/Commands/ImportTradingResearchArtifactsCommand.php`

Files changed:
- `ResearchArtifactService` to support registry lookup.

Acceptance criteria:
- Latest artifact per ticker/type can be resolved.
- Invalid schema artifacts are ignored.

Risk:
- Registry points to deleted files.

Complexity:
- Low to Medium.

### Milestone 4 — Trading Decision Service

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
