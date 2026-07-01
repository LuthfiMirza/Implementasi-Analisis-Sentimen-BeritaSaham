# Sprint 13-17 Uncommitted Checkpoint

Generated on: 2026-07-02

## 1. Branch dan HEAD
- Branch: main
- HEAD: 7ea6ac06d6581b0be27ee00970473c8afdf7aa5d

## 2. Tracked modified files
- app/Services/Trading/RiskEngineService.php
- app/Services/Trading/TradePlanService.php
- app/Services/Trading/TradingDecisionService.php
- config/trading_research.php
- config/trading_risk.php
- config/trading_trade_plan.php
- docs/ROADMAP_AI_TRADING.md
- tests/Feature/TradingDecisionRegistryIntegrationTest.php
- tests/Unit/RiskEngineServiceTest.php
- tests/Unit/TradePlanServiceTest.php
- tests/Unit/TradingDecisionServiceTest.php

## 3. Untracked source files
- app/Services/Trading/CapitalRiskEvaluationService.php
- app/Services/Trading/ExecutionConstraintEvaluationService.php
- app/Services/Trading/ExecutionReadinessService.php
- app/Services/Trading/ExposureAggregationService.php
- app/Services/Trading/PortfolioRiskEvaluationService.php
- app/Services/Trading/PositionManagementCandidateService.php
- app/Services/Trading/PositionManagementPolicyService.php
- app/Services/Trading/PositionManagementSelectionService.php
- app/Services/Trading/PositionManagementService.php
- app/Services/Trading/PositionSizingService.php
- app/Services/Trading/PositionStateEvaluationService.php
- config/trading_execution.php
- config/trading_portfolio_risk.php
- config/trading_position_management.php
- config/trading_position_management_action.php
- config/trading_position_sizing.php

## 4. Untracked tests
- tests/Unit/CapitalRiskEvaluationServiceTest.php
- tests/Unit/ExecutionConstraintEvaluationServiceTest.php
- tests/Unit/ExecutionReadinessServiceTest.php
- tests/Unit/ExposureAggregationServiceTest.php
- tests/Unit/PortfolioRiskEvaluationServiceTest.php
- tests/Unit/PositionManagementCandidateServiceTest.php
- tests/Unit/PositionManagementPolicyServiceTest.php
- tests/Unit/PositionManagementSelectionServiceTest.php
- tests/Unit/PositionManagementServiceTest.php
- tests/Unit/PositionSizingServiceTest.php
- tests/Unit/PositionStateEvaluationServiceTest.php

## 5. Untracked ADR/docs
- docs/adr/ADR-066-capital-context-and-risk-policy.md
- docs/adr/ADR-067-gross-capital-risk-boundary.md
- docs/adr/ADR-068-reference-position-sizing.md
- docs/adr/ADR-069-reference-size-vs-executable-quantity.md
- docs/adr/ADR-070-execution-readiness-boundary.md
- docs/adr/ADR-071-explicit-market-and-cash-constraints.md
- docs/adr/ADR-072-reference-quantity-vs-executable-quantity.md
- docs/adr/ADR-073-no-default-execution-assumptions.md
- docs/adr/ADR-074-explicit-portfolio-context.md
- docs/adr/ADR-075-reference-exposure-aggregation.md
- docs/adr/ADR-076-post-candidate-portfolio-risk.md
- docs/adr/ADR-077-portfolio-evaluation-vs-approval.md
- docs/adr/ADR-078-managed-position-state-boundary.md
- docs/adr/ADR-079-explicit-market-observation-for-position-management.md
- docs/adr/ADR-080-position-condition-vs-management-action.md
- docs/adr/ADR-081-no-trade-journal-position-fallback.md
- docs/adr/ADR-082-position-management-policy-boundary.md
- docs/adr/ADR-083-condition-to-review-candidate-mapping.md
- docs/adr/ADR-084-management-candidate-vs-management-action.md
- docs/adr/ADR-085-management-selection-safety-boundary.md
- docs/checkpoints/SPRINT_13_16_UNCOMMITTED_CHECKPOINT.md
- docs/checkpoints/SPRINT_13_17_UNCOMMITTED_CHECKPOINT.md

## 6. Generated research files
- output/prediction_research/dataset_bumi_with_sentiment.csv
- output/prediction_research/dataset_dewa_with_sentiment.csv
- output/project_status_report_sentimena.md

## 7. Schema baseline Sprint 16.1
- decision schema: trading_decision_v1_13
- service contract: basic_decision_v1_13
- position-management schema: trading_position_management_v1_1
- management policy: trading_position_management_policy_v1
- policy evaluation: trading_position_management_policy_evaluation_v1
- management candidate: trading_position_management_candidate_v1
- management selection: trading_position_management_selection_v1

## 8. Test baseline Sprint 16.1
- Full PHP: php artisan test => 338 passed (1468 assertions)
- Python regression: 58 passed in 4.00s

## 9. Suggested manual commit grouping
- Sprint 13 capital risk and sizing
- Sprint 14 execution readiness
- Sprint 15 portfolio risk
- Sprint 16 position monitoring
- Sprint 16.1 position management policy/candidate/selection
- Sprint 17 portfolio approval and authorization (after completion)
- Generated artifacts excluded unless explicitly decided

## 10. No automatic commit/push confirmation
No git add, commit, push, clean, reset, or destructive checkout was performed for this checkpoint.
