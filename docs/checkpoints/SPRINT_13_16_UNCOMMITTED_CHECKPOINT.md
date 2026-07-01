# Sprint 13-16 Uncommitted Checkpoint

Generated on: 2026-07-02

## 1. Current branch
main

## 2. Current HEAD
7ea6ac06d6581b0be27ee00970473c8afdf7aa5d

## 3. Tracked modified files
app/Services/Trading/RiskEngineService.php
app/Services/Trading/TradePlanService.php
app/Services/Trading/TradingDecisionService.php
config/trading_research.php
config/trading_risk.php
config/trading_trade_plan.php
docs/ROADMAP_AI_TRADING.md
tests/Feature/TradingDecisionRegistryIntegrationTest.php
tests/Unit/RiskEngineServiceTest.php
tests/Unit/TradePlanServiceTest.php
tests/Unit/TradingDecisionServiceTest.php

## 4. Untracked source files
app/Services/Trading/CapitalRiskEvaluationService.php
app/Services/Trading/ExecutionConstraintEvaluationService.php
app/Services/Trading/ExecutionReadinessService.php
app/Services/Trading/ExposureAggregationService.php
app/Services/Trading/PortfolioRiskEvaluationService.php
app/Services/Trading/PositionManagementService.php
app/Services/Trading/PositionSizingService.php
app/Services/Trading/PositionStateEvaluationService.php
config/trading_execution.php
config/trading_portfolio_risk.php
config/trading_position_management.php
config/trading_position_sizing.php

## 5. Untracked test files
tests/Unit/CapitalRiskEvaluationServiceTest.php
tests/Unit/ExecutionConstraintEvaluationServiceTest.php
tests/Unit/ExecutionReadinessServiceTest.php
tests/Unit/ExposureAggregationServiceTest.php
tests/Unit/PortfolioRiskEvaluationServiceTest.php
tests/Unit/PositionManagementServiceTest.php
tests/Unit/PositionSizingServiceTest.php
tests/Unit/PositionStateEvaluationServiceTest.php

## 6. Untracked ADR/documentation
docs/adr/ADR-066-capital-context-and-risk-policy.md
docs/adr/ADR-067-gross-capital-risk-boundary.md
docs/adr/ADR-068-reference-position-sizing.md
docs/adr/ADR-069-reference-size-vs-executable-quantity.md
docs/adr/ADR-070-execution-readiness-boundary.md
docs/adr/ADR-071-explicit-market-and-cash-constraints.md
docs/adr/ADR-072-reference-quantity-vs-executable-quantity.md
docs/adr/ADR-073-no-default-execution-assumptions.md
docs/adr/ADR-074-explicit-portfolio-context.md
docs/adr/ADR-075-reference-exposure-aggregation.md
docs/adr/ADR-076-post-candidate-portfolio-risk.md
docs/adr/ADR-077-portfolio-evaluation-vs-approval.md
docs/adr/ADR-078-managed-position-state-boundary.md
docs/adr/ADR-079-explicit-market-observation-for-position-management.md
docs/adr/ADR-080-position-condition-vs-management-action.md
docs/adr/ADR-081-no-trade-journal-position-fallback.md
docs/checkpoints/SPRINT_13_16_UNCOMMITTED_CHECKPOINT.md

## 7. Generated research artifacts
output/prediction_research/dataset_bumi_with_sentiment.csv
output/prediction_research/dataset_dewa_with_sentiment.csv
output/project_status_report_sentimena.md

## 8. Test baseline terakhir
- Full PHP: php artisan test => 324 passed (1409 assertions)
- Python regression: 58 passed in 3.99s

## 9. Schema versions terakhir
- decision schema: trading_decision_v1_12
- service contract: basic_decision_v1_12
- risk schema: trading_risk_v1_3
- trade-plan schema: trading_trade_plan_v1_2
- execution constraints: trading_execution_constraints_v1
- execution readiness: trading_execution_readiness_v1
- portfolio context: trading_portfolio_context_v1
- position snapshot: trading_position_snapshot_v1
- exposure aggregation: trading_exposure_aggregation_v1
- portfolio risk: trading_portfolio_risk_v1
- managed position: trading_managed_position_v1
- market observation: trading_position_market_observation_v1
- position state: trading_position_state_v1
- position management: trading_position_management_v1

## 10. Suggested manual commit grouping
- Sprint 13 capital risk and sizing
- Sprint 14 execution readiness
- Sprint 15 portfolio risk
- Sprint 16 position monitoring
- Generated artifacts excluded unless explicitly decided

## 11. No automatic commit/push confirmation
No git add, commit, push, clean, reset, or destructive checkout was performed for this checkpoint.
