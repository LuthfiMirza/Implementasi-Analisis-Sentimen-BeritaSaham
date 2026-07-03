# Sprint 13–18.1 Uncommitted Checkpoint

## Current branch
main

## Current HEAD
331d1eb0869d1883ccf2897615d459d20638228b

## Tracked modified files
- `app/Services/Trading/PositionManagementSelectionService.php`
- `app/Services/Trading/PositionManagementService.php`
- `app/Services/Trading/TradingDecisionService.php`
- `config/trading_position_management.php`
- `config/trading_position_management_action.php`
- `config/trading_research.php`
- `docs/ROADMAP_AI_TRADING.md`
- `tests/Unit/PositionManagementSelectionServiceTest.php`
- `tests/Unit/PositionManagementServiceTest.php`
- `tests/Unit/TradingDecisionServiceTest.php`

## Untracked source files
- `app/Services/Trading/PositionManagementActionPolicyService.php`
- `app/Services/Trading/PositionManagementActionPlanService.php`
- `app/Services/Trading/PositionManagementImpactSimulationService.php`
- `config/trading_position_management_plan.php`

## Untracked tests
- `tests/Unit/PositionManagementActionPolicyServiceTest.php`
- `tests/Unit/PositionManagementActionPlanServiceTest.php`
- `tests/Unit/PositionManagementImpactSimulationServiceTest.php`

## Untracked ADR and documentation
- `docs/adr/ADR-094-management-review-candidate-vs-action-proposal.md`
- `docs/adr/ADR-095-explicit-management-action-policy.md`
- `docs/adr/ADR-096-reference-management-action-plan.md`
- `docs/adr/ADR-097-management-portfolio-impact-simulation.md`
- `docs/checkpoints/SPRINT_13_18_1_UNCOMMITTED_CHECKPOINT.md`

## Generated research artifacts
Do not touch or delete:
- `output/prediction_research/dataset_bumi_with_sentiment.csv`
- `output/prediction_research/dataset_dewa_with_sentiment.csv`
- `output/project_status_report_sentimena.md`

## Schema baseline Sprint 18
- Decision schema: `trading_decision_v1_15`
- Service contract: `basic_decision_v1_15`
- Position-management schema: `trading_position_management_v1_2`
- Management-risk schema: `trading_position_management_risk_v1`
- Review-plan schema: `trading_position_management_review_plan_v1`

## Test baseline Sprint 18
Sprint 18 accepted technically before this checkpoint. Sprint 18.1 must re-run PHP tests and Python regression tests after implementation.

## Suggested manual commit grouping
1. Sprint 13–18 accumulated contract foundation changes.
2. Sprint 18.1 management action policy/plan/impact services and config.
3. Sprint 18.1 unit and integration tests.
4. Sprint 18.1 roadmap and ADR documentation.
5. Generated research artifacts, only if intentionally retained by maintainer.

## No automatic git actions
No `git add`, `git commit`, or `git push` is performed automatically. No `git clean`, reset, destructive checkout, generated-file deletion, or `.gitignore` change is performed.
