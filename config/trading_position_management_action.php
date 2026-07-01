<?php
return [
 'policy_schema_version'=>'trading_position_management_policy_v1',
 'policy_evaluation_schema_version'=>'trading_position_management_policy_evaluation_v1',
 'candidate_schema_version'=>'trading_position_management_candidate_v1',
 'selection_schema_version'=>'trading_position_management_selection_v1',
 'supported_policy_conditions'=>['stop_reference_breached','target_reference_reached','protection_reference_missing','market_observation_stale'],
 'supported_review_candidate_types'=>['protection_breach_review','target_reached_review','protection_missing_review','stale_observation_review'],
 'candidate_identity_algorithm'=>'sha256_normalized_json_v1',
 'priority_tie_policy'=>'invalid_on_duplicate_priority_for_active_matches',
 'safety_fallback_action'=>'WAIT',
 'policy_gate_order'=>['position_management_scope','position_state_available','position_state_valid','condition_available','policy_available','policy_schema_valid','policy_reference_only_status','position_id_match','ticker_match','side_match','policy_freshness','supported_condition','enabled_matching_rules','rule_priority_resolution','policy_approval_status','final_policy_classification'],
 'candidate_gate_order'=>['position_state_available','condition_observed','policy_evaluation_available','matched_rule_available','supported_candidate_type','position_identity_match','policy_identity_match','evidence_freshness','candidate_identity_generation','non_executable_capability','final_candidate_classification'],
 'selection_gate_order'=>['decision_scope','position_state_availability','position_state_validity','condition_availability','policy_availability','policy_schema_validity','position_identity_match','ticker_identity_match','side_identity_match','policy_rule_match','management_candidate_availability','candidate_schema_validity','candidate_identity_validity','candidate_evidence_freshness','candidate_policy_approval','management_risk_availability','management_risk_identity_match','management_plan_availability','management_plan_identity_match','portfolio_approval_availability','selection_capability','promotion_capability','execution_capability','final_safety_classification'],
 'capabilities'=>['management_risk'=>'not_implemented','management_plan'=>'not_implemented','portfolio_approval'=>'not_implemented','selection'=>'disabled','promotion'=>'not_implemented','execution'=>'not_implemented'],
 'reason_code_priorities'=>[],
];
