<?php

return [
    'market_constraints_schema_version' => 'trading_market_constraints_v1',
    'cash_context_schema_version' => 'trading_execution_cash_context_v1',
    'execution_cost_schema_version' => 'trading_execution_cost_evidence_v1',
    'liquidity_schema_version' => 'trading_liquidity_evidence_v1',
    'constraint_schema_version' => 'trading_execution_constraints_v1',
    'readiness_schema_version' => 'trading_execution_readiness_v1',
    'supported_intents' => ['long_entry'],
    'constraint_gate_order' => ['candidate_available','candidate_ready','supported_intent','reference_plan_available','reference_plan_materialized','capital_risk_evaluated','position_sizing_reference_sized','candidate_identity_consistency','market_constraints_available','market_constraints_valid','market_constraints_fresh','cash_context_available','cash_context_valid','cash_context_fresh','currency_match','unit_step_alignment','minimum_order_validation','cash_cap_calculation','optional_liquidity_cap_calculation','gross_risk_reconciliation','optional_cost_risk_reconciliation','non_executable_capability'],
    'readiness_gate_order' => ['constraint_evaluation_available','constraint_evaluation_valid','minimum_order_satisfied','cash_sufficiency_known','cash_sufficient','liquidity_status','execution_cost_status','gross_risk_reconciliation','cost_adjusted_risk_status','portfolio_risk_status','broker_capability_status','execution_policy_status','final_reference_readiness_classification'],
    'timestamp_freshness_minutes' => 1440,
    'currency_policy' => 'strict_match',
    'precision' => 6,
    'reconciliation_tolerance' => 0.000001,
    'execution_cost_capability' => 'optional_reference_only',
    'liquidity_capability' => 'optional_reference_only',
    'portfolio_risk_capability' => 'not_implemented',
    'broker_capability' => 'not_implemented',
    'reference_ready_requires_cost_evidence' => false,
    'reference_ready_requires_liquidity_evidence' => false,
    'reason_code_priority' => [],
];
