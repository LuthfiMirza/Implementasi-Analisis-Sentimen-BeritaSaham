<?php

namespace Tests\Unit;

use App\Services\Trading\ActionCandidateService;
use App\Services\Trading\PositionSizingService;
use Tests\TestCase;

class PositionSizingServiceTest extends TestCase
{
    public function test_capital_risk_unavailable(): void
    {
        $sizing = (new PositionSizingService())->size([]);
        $this->assertSame('trading_position_sizing_v1', $sizing['schema_version']);
        $this->assertSame('unavailable', $sizing['status']);
        $this->assertNull($sizing['metrics']['executable_quantity']);
        $this->assertContains('POSITION_SIZING_CAPITAL_RISK_REQUIRED', $sizing['reason_codes']);
    }

    public function test_valid_reference_units_and_notional_are_non_executable(): void
    {
        $candidate = $this->candidate();
        $sizing = (new PositionSizingService())->size($this->context($candidate));
        $this->assertSame('reference_sized', $sizing['status']);
        $this->assertSame(5000.0, $sizing['metrics']['raw_reference_units']);
        $this->assertSame(5000.0, $sizing['metrics']['whole_unit_reference_floor']);
        $this->assertSame(10000.0, $sizing['metrics']['gross_loss_at_reference_units']);
        $this->assertSame(500000.0, $sizing['metrics']['reference_notional']);
        $this->assertNull($sizing['metrics']['executable_quantity']);
        $this->assertSame('not_implemented', $sizing['constraints']['lot_size']['status']);
        $this->assertSame('not_implemented', $sizing['constraints']['cash_availability']['status']);
        $this->assertSame('not_implemented', $sizing['constraints']['portfolio_exposure']['status']);
    }

    public function test_confidence_and_rr_do_not_change_sizing(): void
    {
        $candidate = $this->candidate();
        $base = $this->context($candidate);
        $low = (new PositionSizingService())->size($base + ['confidence'=>50,'rr'=>1.5]);
        $high = (new PositionSizingService())->size($base + ['confidence'=>95,'rr'=>9.0]);
        $this->assertSame($low['metrics']['raw_reference_units'], $high['metrics']['raw_reference_units']);
        $this->assertSame($low['metrics']['whole_unit_reference_floor'], $high['metrics']['whole_unit_reference_floor']);
    }

    public function test_validator_rejects_executable_quantity(): void
    {
        $candidate = $this->candidate();
        $service = new PositionSizingService();
        $sizing = $service->size($this->context($candidate));
        $sizing['metrics']['executable_quantity'] = 5000;
        $this->expectException(\InvalidArgumentException::class);
        $service->validatePositionSizing($sizing);
    }

    protected function context(array $candidate): array
    {
        return ['action_candidate'=>$candidate,'capital_risk'=>['schema_version'=>'trading_capital_risk_v1','status'=>'evaluated_reference','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'metrics'=>['maximum_loss_amount'=>10000.0,'gross_loss_per_unit'=>2.0],'metadata'=>['currency'=>'IDR'],'capital_snapshot'=>['synthetic_test_only'=>true]],'action_risk'=>['metrics'=>['gross_loss_per_unit'=>2.0]],'reference_plan'=>['entry'=>['reference_price'=>100.0]]];
    }
    protected function candidate(): array { return (new ActionCandidateService())->build(['ticker'=>'BUMI','prediction_snapshots'=>[['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','normalized_semantic'=>'directional_up','freshness_status'=>'fresh','generated_at'=>'2026-07-01T09:55:00+07:00']],'prediction_evidence'=>['conflict_status'=>'none'],'artifact_availability'=>['tp_optimizer'=>$this->artifact(true),'sl_optimizer'=>$this->artifact(true)],'evidence_readiness'=>'decision_ready','position_context'=>'no_open_trade','decision_fingerprint_seed'=>'seed']); }
    protected function artifact(bool $decision): array { return ['latest_decision_available'=>$decision,'selected_available'=>$decision,'latest_valid'=>['id'=>1,'checksum'=>str_repeat('a',64)],'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']]; }
}
