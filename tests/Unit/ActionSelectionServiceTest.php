<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\ActionSelectionService;
use Tests\TestCase;

class ActionSelectionServiceTest extends TestCase
{
    public function test_observation_candidate_is_not_selected_and_safety_wait(): void
    {
        $selection = (new ActionSelectionService())->select($this->context($this->candidate('research_ready')));
        $this->assertSame('trading_action_selection_v1', $selection['schema_version']);
        $this->assertSame('candidate_not_ready', $selection['status']);
        $this->assertSame('research_only', $selection['selection_eligibility']);
        $this->assertNull($selection['selected_candidate']);
        $this->assertSame('WAIT', $selection['safety_action']);
    }

    public function test_candidate_ready_without_confidence_risk_plan_is_not_selected(): void
    {
        $candidate = $this->candidate('decision_ready');
        $selection = (new ActionSelectionService())->select($this->context($candidate));
        $this->assertSame('eligible_but_selection_disabled', $selection['status']);
        $this->assertSame('eligible_but_not_selectable', $selection['selection_eligibility']);
        $this->assertContains('ACTION_SELECTION_CONFIDENCE_UNAVAILABLE', $selection['reason_codes']);
        $this->assertContains('ACTION_SELECTION_RISK_UNAVAILABLE', $selection['reason_codes']);
        $this->assertContains('ACTION_SELECTION_TRADE_PLAN_UNAVAILABLE', $selection['reason_codes']);
        $this->assertNull($selection['selected_candidate']);
    }

    public function test_contract_ready_still_not_selected_when_capability_disabled(): void
    {
        $candidate = $this->candidate('decision_ready');
        $context = $this->context($candidate);
        $context['trade_action_confidence'] = ['status'=>'candidate_ready','score'=>80.0,'action'=>'long_entry','action_candidate_id'=>$candidate['candidate_id']];
        $context['decision_risk'] = ['status'=>'available','action_candidate_id'=>$candidate['candidate_id']];
        $context['trade_plan'] = ['status'=>'available','action_candidate_id'=>$candidate['candidate_id']];
        $selection = (new ActionSelectionService())->select($context);
        $this->assertSame('eligible_but_selection_disabled', $selection['status']);
        $this->assertContains('ACTION_SELECTION_CAPABILITY_DISABLED', $selection['reason_codes']);
        $this->assertContains('ACTION_SELECTION_POLICY_NOT_IMPLEMENTED', $selection['reason_codes']);
        $this->assertNull($selection['selected_candidate']);
    }

    public function test_materialized_reference_plan_is_not_selectable_without_execution_readiness(): void
    {
        $candidate = $this->candidate('decision_ready');
        $context = $this->context($candidate);
        $context['trade_action_confidence'] = ['status'=>'candidate_ready','score'=>null,'action'=>'long_entry','action_candidate_id'=>$candidate['candidate_id']];
        $context['decision_risk'] = ['status'=>'evaluated','action_candidate_id'=>$candidate['candidate_id'],'capital_risk'=>['status'=>'not_implemented']];
        $context['trade_plan'] = ['schema_version'=>'trading_trade_plan_v1_1','status'=>'materialized','action_candidate_id'=>$candidate['candidate_id'],'candidate_id'=>$candidate['candidate_id'],'execution_readiness'=>['status'=>'reference_ready','executable'=>false]];

        $selection = (new ActionSelectionService())->select($context);

        $this->assertNull($selection['selected_candidate']);
        $this->assertSame('eligible_but_selection_disabled', $selection['status']);
        $this->assertContains('ACTION_SELECTION_POLICY_NOT_IMPLEMENTED', $selection['reason_codes']);
    }

    public function test_identity_mismatches_are_blockers(): void
    {
        $candidate = $this->candidate('decision_ready');
        $context = $this->context($candidate);
        $context['trade_action_confidence'] = ['status'=>'candidate_ready','score'=>80.0,'action'=>'long_entry','action_candidate_id'=>'bad'];
        $context['decision_risk'] = ['status'=>'available','action_candidate_id'=>'bad'];
        $context['trade_plan'] = ['status'=>'available','action_candidate_id'=>'bad'];
        $selection = (new ActionSelectionService())->select($context);
        $this->assertContains('ACTION_SELECTION_CONFIDENCE_IDENTITY_MISMATCH', $selection['reason_codes']);
        $this->assertContains('ACTION_SELECTION_RISK_IDENTITY_MISMATCH', $selection['reason_codes']);
        $this->assertContains('ACTION_SELECTION_TRADE_PLAN_IDENTITY_MISMATCH', $selection['reason_codes']);
    }

    public function test_safety_no_trade_and_gate_order(): void
    {
        $selection = (new ActionSelectionService())->select($this->context(null, 'NO_TRADE'));
        $this->assertSame('NO_TRADE', $selection['safety_action']);
        $this->assertContains('SAFETY_ACTION_NO_TRADE_SELECTED', $selection['reason_codes']);
        $this->assertSame(config('trading_action.selection_gate_order'), array_column($selection['selection_gates'], 'gate'));
    }

    protected function context(?array $candidate, string $safety = 'WAIT'): array
    {
        return ['action_candidate'=>$candidate,'trade_action_confidence'=>['status'=>'unavailable'],'decision_risk'=>['status'=>'unavailable'],'trade_plan'=>['status'=>'unavailable'],'safety_action'=>$safety];
    }

    protected function candidate(string $readiness): array
    {
        $svc = new ActionCandidateService();
        $decision = $readiness === 'decision_ready';
        return $svc->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact($decision),'sl_optimizer'=>$this->artifact($decision)],'evidence_readiness'=>$readiness,'position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']);
    }

    protected function artifact(bool $decision): array
    {
        return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }
}
