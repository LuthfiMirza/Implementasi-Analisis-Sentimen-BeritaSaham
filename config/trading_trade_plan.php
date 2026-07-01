<?php

return [
    'trade_plan_schema_version' => 'trading_trade_plan_v1_2',
    'reference_plan_schema_version' => 'trading_reference_trade_plan_v1',
    'entry_reference_schema_version' => 'trading_entry_reference_v1',
    'supported_intents' => ['long_entry'],
    'supported_parameter_types' => ['percentage'],
    'materialization_gate_order' => ['candidate_available','candidate_valid','candidate_ready','supported_intent','selected_parameters_available','selected_parameters_valid','candidate_identity_match','tp_source_decision_usable','sl_source_decision_usable','source_dependencies_resolved','source_fresh','source_not_quarantined','action_risk_available','action_risk_evaluated','action_risk_identity_match','risk_geometry_consistency','entry_reference_available','entry_reference_valid','entry_reference_identity_match','entry_reference_freshness','reference_price_materialization','execution_capability'],
    'entry_reference_freshness_minutes' => 120,
    'rounding_precision' => 6,
    'execution_capability' => 'not_implemented',
    'holding_capability' => 'not_implemented',
    'reentry_capability' => 'not_implemented',
    'position_sizing_capability' => 'not_implemented',
    'position_management_capability' => 'not_implemented',
];
