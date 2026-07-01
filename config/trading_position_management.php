<?php
return [
 'managed_position_schema_version'=>'trading_managed_position_v1',
 'market_observation_schema_version'=>'trading_position_market_observation_v1',
 'position_state_schema_version'=>'trading_position_state_v1',
 'position_management_schema_version'=>'trading_position_management_v1_2',
 'supported_sides'=>['long'],
 'observation_freshness_minutes'=>1440,
 'pnl_precision'=>6,
 'position_state_gate_order'=>['position_available','position_schema_valid','position_status_open','supported_position_type','ticker_identity_match','currency_consistency','entry_price_validity','quantity_validity','opened_at_validity','market_observation_available','market_observation_valid','market_observation_fresh','market_identity_match','reference_pnl_calculation','optional_stop_reference_validation','optional_target_reference_validation','stop_condition_evaluation','target_condition_evaluation','final_state_classification'],
 'management_gate_order'=>['decision_scope','position_state_available','position_state_valid','monitoring_evidence_readiness','protection_reference_completeness','condition_observation','management_action_capability','management_selection_capability','execution_capability','final_management_classification'],
 'capabilities'=>['action_selection'=>'not_implemented','execution'=>'not_implemented'],
];
