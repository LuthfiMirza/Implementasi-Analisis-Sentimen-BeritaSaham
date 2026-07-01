<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use Tests\TestCase;

class ActionCandidateServiceTest extends TestCase
{
    public function test_research_only_evidence_is_observation_only_not_candidate_ready(): void
    {
        $candidate = (new ActionCandidateService())->build($this->context('research_ready'));

        $this->assertSame('trading_action_candidate_v1', $candidate['schema_version']);
        $this->assertSame('observation_only', $candidate['status']);
        $this->assertSame('observation', $candidate['intent']);
        $this->assertSame('research_only', $candidate['eligibility']);
        $this->assertNull($candidate['candidate_id']);
        $this->assertSame('non_executable', $candidate['execution_status']);
        $this->assertContains('ACTION_CANDIDATE_OBSERVATION_ONLY', $candidate['reason_codes']);
        $this->assertContains('DECISION_USABLE_TP_REQUIRED_FOR_CANDIDATE', $candidate['reason_codes']);
    }

    public function test_regime_only_and_directional_down_do_not_create_long_entry(): void
    {
        $regime = $this->context('decision_ready');
        $regime['prediction_snapshots'] = [['available'=>true,'variant'=>'dewa_regime','semantic_role'=>'regime','normalized_semantic'=>'regime_move','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']];
        $candidate = (new ActionCandidateService())->build($regime);
        $this->assertNotSame('candidate_ready', $candidate['status']);
        $this->assertContains('LONG_ENTRY_CANDIDATE_REQUIRES_DIRECTIONAL_UP', $candidate['reason_codes']);

        $down = $this->context('decision_ready');
        $down['prediction_snapshots'][0]['normalized_semantic'] = 'directional_down';
        $candidate = (new ActionCandidateService())->build($down);
        $this->assertNotSame('candidate_ready', $candidate['status']);
        $this->assertContains('DIRECTIONAL_SIGNAL_NOT_ELIGIBLE', $candidate['reason_codes']);
    }

    public function test_synthetic_decision_ready_candidate_has_deterministic_id(): void
    {
        $service = new ActionCandidateService();
        $first = $service->build($this->context('decision_ready'));
        $second = $service->build($this->context('decision_ready'));

        $this->assertSame('candidate_ready', $first['status']);
        $this->assertSame('long_entry', $first['intent']);
        $this->assertSame('eligible_for_risk_evaluation', $first['eligibility']);
        $this->assertSame($first['candidate_id'], $second['candidate_id']);
        $this->assertContains('ACTION_CANDIDATE_READY', $first['reason_codes']);
        $this->assertContains('ACTION_PROMOTION_NOT_IMPLEMENTED', $first['reason_codes']);
    }

    public function test_prediction_and_checksum_change_candidate_id(): void
    {
        $service = new ActionCandidateService();
        $first = $service->build($this->context('decision_ready'));
        $changedPrediction = $this->context('decision_ready');
        $changedPrediction['prediction_snapshots'][0]['generated_at'] = '2026-07-01T09:56:00+07:00';
        $second = $service->build($changedPrediction);
        $changedArtifact = $this->context('decision_ready');
        $changedArtifact['artifact_availability']['tp_optimizer']['latest_valid']['checksum'] = str_repeat('b', 64);
        $third = $service->build($changedArtifact);

        $this->assertNotSame($first['candidate_id'], $second['candidate_id']);
        $this->assertNotSame($first['candidate_id'], $third['candidate_id']);
    }

    public function test_open_trade_and_invalid_context_are_blocked_or_invalid(): void
    {
        $open = $this->context('decision_ready');
        $open['position_context'] = 'open_trade';
        $candidate = (new ActionCandidateService())->build($open);
        $this->assertSame('blocked', $candidate['status']);
        $this->assertContains('POSITION_MANAGEMENT_CANDIDATE_NOT_IMPLEMENTED', $candidate['reason_codes']);

        $invalid = $this->context('decision_ready');
        $invalid['position_context'] = 'invalid_open_trade';
        $candidate = (new ActionCandidateService())->build($invalid);
        $this->assertSame('invalid', $candidate['status']);
    }

    public function test_gate_order_and_skipped_gate_nullable(): void
    {
        $invalid = $this->context('decision_ready');
        $invalid['position_context'] = 'invalid_open_trade';
        $candidate = (new ActionCandidateService())->build($invalid);
        $gates = array_column($candidate['eligibility_gates'], 'gate');
        $this->assertSame(config('trading_action.candidate_gate_order'), $gates);
        $this->assertTrue(collect($candidate['eligibility_gates'])->where('evaluated', false)->every(fn($g) => $g['passed'] === null));
    }

    protected function context(string $readiness): array
    {
        $decision = $readiness === 'decision_ready';
        return [
            'ticker' => 'BUMI',
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'prediction_snapshots' => [['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],
            'prediction_evidence' => ['conflict_status' => 'none'],
            'artifact_availability' => ['tp_optimizer'=>$this->artifact('tp_optimizer', $decision), 'sl_optimizer'=>$this->artifact('sl_optimizer', $decision)],
            'evidence_readiness' => $readiness,
            'position_context' => 'no_open_trade',
            'decision_fingerprint_seed' => 'seed',
        ];
    }

    protected function artifact(string $type, bool $decision): array
    {
        return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a', 64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }
}
