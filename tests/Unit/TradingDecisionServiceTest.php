<?php

namespace Tests\Unit;

use App\Services\Trading\DecisionEvidenceService;
use App\Services\Trading\TradingDecisionService;
use Mockery;
use Tests\TestCase;

class TradingDecisionServiceTest extends TestCase
{
    public function test_research_only_evidence_produces_wait_with_null_engine_fields(): void
    {
        $result = $this->service($this->researchEvidence())->decide($this->input());

        $this->assertSame('trading_decision_v1_8', $result['schema_version']);
        $this->assertSame('WAIT', $result['action']);
        $this->assertSame('safe_downgrade', $result['action_status']);
        $this->assertSame('research_only', $result['recommendation_quality']);
        $this->assertSame('trading_confidence_v1_1', $result['confidence']['schema_version']);
        $this->assertSame('research_only', $result['confidence_status']);
        $this->assertNull($result['confidence']['trade_action_confidence']['score']);
        $this->assertSame('available', $result['confidence']['safety_decision_confidence']['status']);
        $this->assertSame('trading_risk_v1_1', $result['risk']['schema_version']);
        $this->assertSame('trading_action_risk_v1', $result['risk']['action_specific_risk']['schema_version']);
        $this->assertSame('trading_trade_plan_v1_1', $result['trade_plan']['schema_version']);
        $this->assertSame('unavailable', $result['risk']['decision_risk']['status']);
        $this->assertSame('unavailable', $result['trade_plan']['status']);
        $this->assertNull($result['risk']['decision_risk']['risk_reward_ratio']);
        $this->assertNull($result['trade_plan']['take_profit']['price']);
        $this->assertNull($result['trade_plan']['stop_loss']['price']);
        $this->assertNull($result['risk']['position_sizing']['recommended_quantity']);
        $this->assertContains('NO_DECISION_USABLE_TP', $result['reason_codes']);
        $this->assertContains('NO_DECISION_USABLE_SL', $result['reason_codes']);
        $this->assertContains('SAFE_DOWNGRADE_WAIT', $result['reason_codes']);
        $this->assertSame('research_ready', $result['evidence_readiness']);
        $this->assertSame('basic_only', $result['capability_readiness']);
        $this->assertSame('blocked', $result['action_eligibility']);
        $this->assertSame('trading_action_candidate_v1', $result['action_candidate']['schema_version']);
        $this->assertSame('observation_only', $result['action_candidate']['status']);
        $this->assertNull($result['action_candidate']['candidate_id']);
        $this->assertSame('trading_action_selection_v1', $result['action_selection']['schema_version']);
        $this->assertSame('WAIT', $result['action_selection']['safety_action']);
        $this->assertNull($result['action_selection']['selected_candidate']);
        $this->assertSame('trading_action_promotion_v1', $result['action_promotion']['schema_version']);
        $this->assertSame('not_promoted', $result['action_promotion']['status']);
        $this->assertNull($result['action_promotion']['promoted_action']);
        $this->assertNull($result['action_promotion']['executable_action']);
        $this->assertSame('entry_evaluation', $result['decision_scope']);
        $this->assertSame('no_open_trade', $result['position_context']);
        $this->assertSame('not_required', $result['position_management_status']);
        $this->assertNotEmpty($result['metadata']['decision_fingerprint']);
        $this->assertNotContains($result['action'], ['BUY','ACCUMULATE','BUY_BACK','SELL']);
    }

    public function test_invalid_ticker_missing_prediction_invalid_probability_and_stale_prediction_are_no_trade(): void
    {
        $service = $this->service([]);
        $cases = [
            array_merge($this->input(), ['ticker' => 'ZZZZ']),
            array_merge($this->input(), ['prediction' => ['available' => false]]),
            array_replace_recursive($this->input(), ['prediction' => ['probability' => 1.5]]),
            array_replace_recursive($this->input(), ['prediction' => ['generated_at' => '2026-07-01T01:00:00+07:00']]),
        ];
        foreach ($cases as $case) {
            $result = $service->decide($case);
            $this->assertSame('NO_TRADE', $result['action']);
            $this->assertContains('SAFE_DOWNGRADE_NO_TRADE', $result['reason_codes']);
        }
    }

    public function test_dewa_regime_move_is_not_directional_up(): void
    {
        $input = $this->input('DEWA');
        $input['prediction']['variant'] = 'dewa_regime';
        $input['prediction']['predicted_direction'] = null;
        $input['prediction']['predicted_regime'] = 'move';

        $result = $this->service($this->researchEvidence('DEWA'))->decide($input);

        $this->assertSame('regime_move', $result['prediction_snapshot']['normalized_semantic']);
        $this->assertNotSame('directional_up', $result['prediction_snapshot']['normalized_semantic']);
        $this->assertSame('WAIT', $result['action']);
    }

    public function test_multiple_directional_and_regime_predictions_are_supported(): void
    {
        $input = $this->input('DEWA');
        unset($input['prediction']);
        $input['predictions'] = [
            ['available'=>true,'variant'=>'dewa_technical','semantic_role'=>'directional','predicted_value'=>'up','probability'=>0.68,'generated_at'=>'2026-07-01T09:55:00+07:00'],
            ['available'=>true,'variant'=>'dewa_regime','semantic_role'=>'regime','predicted_value'=>'move','probability'=>0.74,'generated_at'=>'2026-07-01T09:55:00+07:00'],
        ];

        $result = $this->service($this->researchEvidence('DEWA'))->decide($input);

        $this->assertCount(2, $result['prediction_snapshots']);
        $this->assertSame('supportive', $result['prediction_evidence']['agreement_status']);
        $this->assertSame('directional_up', $result['prediction_evidence']['directional_semantic']);
        $this->assertSame('regime_move', $result['prediction_evidence']['regime_semantic']);
        $this->assertContains('MULTIPLE_PREDICTIONS_AVAILABLE', $result['reason_codes']);
    }

    public function test_regime_only_does_not_become_directional_buy(): void
    {
        $input = $this->input('DEWA');
        unset($input['prediction']);
        $input['predictions'] = [['available'=>true,'variant'=>'dewa_regime','semantic_role'=>'regime','predicted_value'=>'move','probability'=>0.74,'generated_at'=>'2026-07-01T09:55:00+07:00']];

        $result = $this->service($this->researchEvidence('DEWA'))->decide($input);

        $this->assertSame('WAIT', $result['action']);
        $this->assertSame('regime_move', $result['prediction_snapshots'][0]['normalized_semantic']);
        $this->assertContains('REGIME_ONLY_NOT_DIRECTIONAL', $result['reason_codes']);
        $this->assertContains('DIRECTIONAL_PREDICTION_MISSING', $result['reason_codes']);
    }

    public function test_duplicate_conflicting_and_contradictory_predictions_are_blocked(): void
    {
        $input = $this->input();
        unset($input['prediction']);
        $input['predictions'] = [
            ['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','predicted_value'=>'up','probability'=>0.7,'generated_at'=>'2026-07-01T09:55:00+07:00'],
            ['available'=>true,'variant'=>'bumi_technical','semantic_role'=>'directional','predicted_value'=>'up','probability'=>0.7,'generated_at'=>'2026-07-01T09:55:00+07:00'],
        ];
        $duplicate = $this->service($this->researchEvidence())->decide($input);
        $this->assertSame('NO_TRADE', $duplicate['action']);
        $this->assertContains('DUPLICATE_PREDICTION', $duplicate['reason_codes']);

        $input['predictions'][1]['variant'] = 'bumi_technical_alt';
        $input['predictions'][1]['predicted_value'] = 'down';
        $conflict = $this->service($this->researchEvidence())->decide($input);
        $this->assertSame('NO_TRADE', $conflict['action']);
        $this->assertContains('PREDICTION_CONFLICT', $conflict['reason_codes']);

        $legacy = $this->input();
        $legacy['predictions'] = [['available'=>true,'variant'=>'other','semantic_role'=>'directional','predicted_value'=>'down','probability'=>0.4,'generated_at'=>'2026-07-01T09:55:00+07:00']];
        $bad = $this->service($this->researchEvidence())->decide($legacy);
        $this->assertContains('CONFLICTING_PREDICTION_INPUTS', $bad['reason_codes']);
    }

    public function test_unknown_prediction_semantics_is_safe_no_trade(): void
    {
        $input = $this->input();
        $input['prediction']['predicted_direction'] = 'moon';

        $result = $this->service($this->researchEvidence())->decide($input);

        $this->assertSame('NO_TRADE', $result['action']);
        $this->assertContains('UNKNOWN_PREDICTION_SEMANTICS', $result['reason_codes']);
    }

    public function test_artifact_stale_quarantined_and_dependency_mismatch_block_decision(): void
    {
        $evidence = $this->researchEvidence();
        $evidence['tp_optimizer']['is_stale'] = true;
        $evidence['sl_optimizer']['is_quarantined'] = true;
        $evidence['trade_episode_dataset']['dependency_status'] = ['checksum_mismatch'];

        $result = $this->service($evidence)->decide($this->input());

        $this->assertSame('NO_TRADE', $result['action']);
        $this->assertContains('ARTIFACT_STALE', $result['reason_codes']);
        $this->assertContains('ARTIFACT_QUARANTINED', $result['reason_codes']);
        $this->assertContains('DEPENDENCY_CHECKSUM_MISMATCH', $result['reason_codes']);
    }

    public function test_high_unclassified_atr_and_extreme_winner_are_warnings(): void
    {
        $result = $this->service($this->researchEvidence('DEWA'))->decide($this->input('DEWA'));

        $this->assertContains('HIGH_UNCLASSIFIED_RATE', $result['reason_codes']);
        $this->assertContains('ATR_FAMILY_UNAVAILABLE', $result['reason_codes']);
        $this->assertContains('EXTREME_WINNER_DEPENDENCY', $result['reason_codes']);
    }

    public function test_synthetic_decision_ready_still_does_not_emit_buy(): void
    {
        $result = $this->service($this->decisionReadyEvidence())->decide($this->input());

        $this->assertSame('WAIT', $result['action']);
        $this->assertSame('unsupported', $result['action_status']);
        $this->assertSame('decision_ready', $result['recommendation_quality']);
        $this->assertSame('decision_ready', $result['evidence_readiness']);
        $this->assertSame('eligible_but_not_supported', $result['action_eligibility']);
        $this->assertNull($result['confidence']['trade_action_confidence']['score']);
        $this->assertSame('unavailable', $result['risk']['decision_risk']['status']);
        $this->assertSame('unavailable', $result['trade_plan']['status']);
        $this->assertNull($result['risk']['decision_risk']['risk_reward_ratio']);
        $this->assertNull($result['trade_plan']['take_profit']['price']);
        $this->assertSame('candidate_ready', $result['action_candidate']['status']);
        $this->assertSame('long_entry', $result['action_candidate']['intent']);
        $this->assertNotEmpty($result['action_candidate']['candidate_id']);
        $this->assertSame('non_executable', $result['action_candidate']['execution_status']);
        $this->assertSame('eligible_for_risk_evaluation', $result['action_candidate']['eligibility']);
        $this->assertSame('candidate_ready', $result['confidence']['trade_action_confidence']['status']);
        $this->assertSame($result['action_candidate']['candidate_id'], $result['confidence']['trade_action_confidence']['action_candidate_id']);
        $this->assertNull($result['action_selection']['selected_candidate']);
        $this->assertSame('eligible_but_selection_disabled', $result['action_selection']['status']);
        $this->assertSame('not_promoted', $result['action_promotion']['status']);
        $this->assertNull($result['action_promotion']['promoted_action']);
        $this->assertNull($result['action_promotion']['executable_action']);
        $this->assertContains('ACTION_PROMOTION_POLICY_NOT_IMPLEMENTED', $result['reason_codes']);
        $this->assertContains('ACTION_SELECTION_NOT_IMPLEMENTED', $result['reason_codes']);
        $this->assertContains('ACTION_ELIGIBLE_BUT_NOT_SUPPORTED', $result['reason_codes']);
        $this->assertNotContains($result['action'], ['BUY','ACCUMULATE','BUY_BACK','SELL','CUT_LOSS']);
    }

    public function test_synthetic_materialized_reference_plan_remains_wait_and_unselected(): void
    {
        $service = $this->service($this->decisionReadyEvidence());
        $candidateSeed = $service->decide($this->input())['action_candidate'];
        $input = $this->input();
        $input['selected_parameters'] = $this->selectedParameters($candidateSeed);
        $input['entry_reference'] = $this->entryReference($candidateSeed);

        $result = $service->decide($input);

        $this->assertSame('trading_decision_v1_8', $result['schema_version']);
        $this->assertSame('trading_trade_plan_v1_1', $result['trade_plan']['schema_version']);
        $this->assertSame('materialized', $result['trade_plan']['reference_plan']['status']);
        $this->assertSame(100.0, $result['trade_plan']['reference_plan']['entry']['reference_price']);
        $this->assertSame(105.0, $result['trade_plan']['reference_plan']['take_profit']['reference_price']);
        $this->assertSame(98.0, $result['trade_plan']['reference_plan']['stop_loss']['reference_price']);
        $this->assertSame(2.5, $result['trade_plan']['reference_plan']['risk_geometry']['gross_reward_risk_ratio']);
        $this->assertSame('reference_ready', $result['trade_plan']['execution_readiness']['status']);
        $this->assertFalse($result['trade_plan']['execution_readiness']['executable']);
        $this->assertNull($result['trade_plan']['position_sizing']['quantity']);
        $this->assertNull($result['action_selection']['selected_candidate']);
        $this->assertNull($result['action_promotion']['promoted_action']);
        $this->assertNull($result['action_promotion']['executable_action']);
        $this->assertSame('WAIT', $result['action']);
        $this->assertNotContains($result['action'], ['BUY','SELL','HOLD']);
    }

    public function test_valid_open_trade_is_position_management_without_hold(): void
    {
        $input = $this->input();
        $input['open_trade'] = ['id'=>'T1','ticker'=>'BUMI','status'=>'open','entry_date'=>'2026-06-30','entry_price'=>100,'quantity'=>100];
        $result = $this->service($this->researchEvidence())->decide($input);
        $this->assertSame('position_management', $result['decision_scope']);
        $this->assertSame('open_trade', $result['position_context']);
        $this->assertSame('not_implemented', $result['position_management_status']);
        $this->assertContains('OPEN_TRADE_PRESENT', $result['reason_codes']);
        $this->assertContains('POSITION_MANAGEMENT_NOT_IMPLEMENTED', $result['reason_codes']);
        $this->assertNotSame('HOLD', $result['action']);

        $input['open_trade']['entry_price'] = 0;
        $invalid = $this->service($this->researchEvidence())->decide($input);
        $this->assertSame('NO_TRADE', $invalid['action']);
        $this->assertSame('invalid_open_trade', $invalid['position_context']);
        $this->assertContains('OPEN_TRADE_INVALID', $invalid['reason_codes']);
    }

    public function test_fingerprint_changes_with_prediction_and_artifact_checksum(): void
    {
        $service = $this->service($this->researchEvidence());
        $first = $service->decide($this->input());
        $changedPrediction = $this->input();
        $changedPrediction['prediction']['probability'] = 0.71;
        $second = $service->decide($changedPrediction);
        $this->assertNotSame($first['metadata']['decision_fingerprint'], $second['metadata']['decision_fingerprint']);

        $evidence = $this->researchEvidence();
        $evidence['tp_optimizer']['latest_valid']['checksum'] = str_repeat('b', 64);
        $third = $this->service($evidence)->decide($this->input());
        $this->assertNotSame($first['metadata']['decision_fingerprint'], $third['metadata']['decision_fingerprint']);
    }

    public function test_output_is_deterministic_and_reason_codes_are_ordered(): void
    {
        $service = $this->service($this->researchEvidence());
        $first = $service->decide($this->input());
        $second = $service->decide($this->input());

        $this->assertSame($first, $second);
        $ordered = $first['reason_codes'];
        $this->assertSame($ordered, array_values(array_unique($ordered)));
        $service->validateDecisionResult($first);
    }

    protected function service(array $evidence): TradingDecisionService
    {
        $mock = Mockery::mock(DecisionEvidenceService::class);
        $mock->shouldReceive('resolve')->andReturn($evidence);
        return new TradingDecisionService($mock);
    }

    protected function input(string $ticker = 'BUMI'): array
    {
        return [
            'ticker' => $ticker,
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'prediction' => [
                'available' => true,
                'variant' => strtolower($ticker).'_technical',
                'predicted_direction' => 'up',
                'predicted_regime' => null,
                'probability' => 0.7,
                'generated_at' => '2026-07-01T09:55:00+07:00',
                'schema_version' => null,
            ],
            'market_context' => ['current_price' => 0, 'market_open' => null, 'data_timestamp' => null],
            'open_trade' => null,
        ];
    }

    protected function researchEvidence(string $ticker = 'BUMI'): array
    {
        $base = [];
        foreach (['trade_episode_dataset','tp_optimizer','sl_optimizer','reentry_research','walk_forward_event_dataset','event_dataset_quality'] as $type) {
            $base[$type] = $this->artifactEvidence($ticker, $type, false, true, ['resolved']);
        }
        $base['reentry_research']['warnings'] = $ticker === 'DEWA'
            ? ['high_unclassified_rate', 'ATR family unavailable', 'extreme_winner_dependency']
            : ['ATR family unavailable', 'extreme_winner_dependency'];
        return $base;
    }

    protected function decisionReadyEvidence(string $ticker = 'BUMI'): array
    {
        $evidence = $this->researchEvidence($ticker);
        foreach (['tp_optimizer','sl_optimizer'] as $type) {
            $evidence[$type]['latest_decision_available'] = true;
            $evidence[$type]['selected_available'] = true;
            $evidence[$type]['latest_decision'] = $evidence[$type]['latest_valid'];
        }
        return $evidence;
    }

    protected function artifactEvidence(string $ticker, string $type, bool $decision, bool $research, array $deps): array
    {
        $snapshot = ['id' => 1, 'ticker' => $ticker, 'artifact_type' => $type, 'schema_version' => $type.'_v1', 'checksum' => str_repeat('a', 64), 'generated_at' => '2026-07-01T00:00:00+00:00', 'validation_status' => 'valid', 'usage_tier' => $decision ? 'decision_usable' : 'research_only', 'quality_grade' => 'warning', 'selected_available' => $decision, 'is_stale' => false, 'is_quarantined' => false, 'dependency_status' => $deps];
        return ['latest_valid_available' => true, 'latest_research_available' => $research, 'latest_decision_available' => $decision, 'latest_valid' => $snapshot, 'latest_research' => $research ? $snapshot : null, 'latest_decision' => $decision ? $snapshot : null, 'quality_grade' => 'warning', 'selected_available' => $decision, 'is_stale' => false, 'is_quarantined' => false, 'dependency_status' => $deps, 'warnings' => []];
    }

    protected function selectedParameters(array $candidate): array
    {
        return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->parameterSource('tp_optimizer',101)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->parameterSource('sl_optimizer',102)],'generated_at'=>'2026-07-01T09:55:00+07:00','synthetic_test_only'=>true];
    }

    protected function parameterSource(string $type, int $id): array
    {
        return ['registry_artifact_id'=>$id,'artifact_type'=>$type,'schema_version'=>$type.'_v1','checksum'=>str_repeat('a',64),'usage_tier'=>'decision_usable','stale'=>false,'quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function entryReference(array $candidate): array
    {
        return ['schema_version'=>'trading_entry_reference_v1','ticker'=>'BUMI','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'fixture-entry-100'],'executable'=>false,'synthetic_test_only'=>true];
    }
}
