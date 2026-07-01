<?php
return [
 'management_risk_schema_version'=>'trading_position_management_risk_v1',
 'review_plan_schema_version'=>'trading_position_management_review_plan_v1',
 'supported_candidate_types'=>['protection_breach_review','target_reached_review','protection_missing_review','stale_observation_review'],
 'numeric_precision'=>6,
 'metric_consistency_tolerance'=>0.000001,
 'stop_breach_formula_policy'=>'stop_minus_current_over_stop',
 'target_exceedance_formula_policy'=>'current_minus_target_over_target',
 'supported_review_checks'=>['confirm_current_market_observation','confirm_position_identity','confirm_position_quantity','confirm_protection_reference','confirm_condition_persistence','confirm_management_risk_context','management_action_policy_required','management_portfolio_approval_required','execution_authorization_required'],
 'management_action_plan_capability'=>'not_implemented',
 'portfolio_approval_capability'=>'not_implemented',
 'execution_authorization_capability'=>'not_implemented',
 'risk_gate_order'=>['position_management_scope','position_state_available','position_state_valid','management_candidate_available','management_candidate_valid','candidate_type_supported','policy_evaluation_available','policy_rule_matched','position_identity_match','candidate_identity_match','condition_match','observation_freshness','canonical_pnl_consistency','optional_stop_reference_availability','optional_target_reference_availability','stop_risk_metric_calculation','target_risk_metric_calculation','net_risk_capability','portfolio_impact_capability','non_executable_classification'],
 'review_plan_gate_order'=>['position_management_scope','management_candidate_available','management_candidate_valid','management_risk_available','management_risk_valid','candidate_identity_match','policy_identity_match','condition_consistency','required_evidence_classification','unavailable_evidence_classification','review_check_generation','management_action_plan_capability','management_approval_capability','execution_authorization_capability','non_executable_classification'],
 'reason_code_priorities'=>[],
];
