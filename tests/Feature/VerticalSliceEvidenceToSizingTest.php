<?php

namespace Tests\Feature;

use App\Models\TradeResearchArtifact;
use App\Services\Research\ResearchArtifactRegistryService;
use App\Services\Research\ResearchArtifactValidationService;
use App\Services\Trading\TradingDecisionService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class VerticalSliceEvidenceToSizingTest extends TestCase
{
    use RefreshDatabase;

    protected string $artifactRoot;

    protected function setUp(): void
    {
        parent::setUp();

        $this->artifactRoot = storage_path('framework/testing/vertical_slice_'.uniqid());
        File::ensureDirectoryExists($this->artifactRoot);

        $decision = config('trading_research.decision');
        $decision['supported_tickers'] = array_values(array_unique(array_merge($decision['supported_tickers'], ['SYNTH'])));
        $decision['prediction_requirements']['SYNTH'] = ['directional_required' => true, 'regime_optional' => true, 'regime_only_policy' => 'wait'];

        config([
            'trading_research.allowed_roots' => [$this->artifactRoot],
            'trading_research.decision' => $decision,
            'trading_research.staleness_days' => array_fill_keys([
                'trade_episode_dataset',
                'tp_optimizer',
                'sl_optimizer',
                'walk_forward_event_dataset',
                'event_dataset_quality',
                'reentry_research',
            ], 3650),
        ]);

        app()->forgetInstance(ResearchArtifactValidationService::class);
        app()->forgetInstance(ResearchArtifactRegistryService::class);
        app()->forgetInstance(TradingDecisionService::class);
    }

    protected function tearDown(): void
    {
        if (isset($this->artifactRoot)) {
            File::deleteDirectory($this->artifactRoot);
        }

        parent::tearDown();
    }

    public function test_golden_fixture_reaches_reference_sized_and_reference_ready_before_final_safety_boundary(): void
    {
        // Fixture assumption: this represents decision-grade evidence under the current validators;
        // if the definition of decision-grade changes, this fixture must be reviewed.
        $this->registerGoldenDecisionArtifacts('SYNTH');

        $service = app(TradingDecisionService::class);
        $candidate = $service->decide($this->baseInput('SYNTH'))['action_candidate'];
        $input = $this->goldenInput('SYNTH', $candidate);

        $result = $service->decide($input);

        $this->assertSame('decision_ready', $result['evidence_readiness']);
        $this->assertSame('candidate_ready', $result['action_candidate']['status']);
        $this->assertNotEmpty($result['action_candidate']['candidate_id']);

        $this->assertSame('evaluated', $result['risk']['action_specific_risk']['status']);
        $this->assertIsNumeric($result['risk']['action_specific_risk']['metrics']['entry_price']);
        $this->assertIsNumeric($result['risk']['action_specific_risk']['metrics']['take_profit_price']);
        $this->assertIsNumeric($result['risk']['action_specific_risk']['metrics']['stop_loss_price']);
        $this->assertIsNumeric($result['risk']['action_specific_risk']['metrics']['gross_loss_per_unit']);

        $this->assertSame('materialized', $result['trade_plan']['reference_plan']['status']);
        $this->assertSame($result['action_candidate']['candidate_id'], $result['trade_plan']['reference_plan']['candidate_id']);

        $this->assertSame('evaluated_reference', $result['risk']['capital_risk']['status'], json_encode($result['risk']['capital_risk'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        $this->assertNotNull($result['risk']['capital_risk']['metrics']['maximum_loss_amount']);
        $this->assertNotNull($result['risk']['capital_risk']['metrics']['gross_loss_per_unit']);

        $this->assertSame('reference_sized', $result['risk']['position_sizing']['status']);
        $this->assertNotNull($result['risk']['position_sizing']['metrics']['raw_reference_units']);
        $this->assertNotNull($result['risk']['position_sizing']['metrics']['whole_unit_reference_floor']);

        $this->assertSame('reference_ready', $result['trade_plan']['execution_readiness']['status']);
        $this->assertNotNull($result['trade_plan']['execution_readiness']['reference_quantity']);

        $message = 'Chain reaches reference_sized; BUY executable blocked by production schema/validator/safety by design, NOT by broken seam.';
        $this->assertNull($result['trade_plan']['execution_readiness']['executable_quantity'], $message);
        $this->assertNull($result['action_selection']['selected_candidate'], $message);
        $this->assertContains($result['action'], ['WAIT', 'NO_TRADE'], $message);
        $this->assertContains('ACTION_CAPABILITY_NOT_IMPLEMENTED', $result['reason_codes'], $message);
        $this->assertContains('ACTION_SELECTION_NOT_IMPLEMENTED', $result['reason_codes'], $message);
    }

    public function test_research_only_path_stays_safe_and_does_not_reach_candidate_or_sizing(): void
    {
        $this->registerResearchOnlyArtifacts('SYNTH');

        $result = app(TradingDecisionService::class)->decide($this->baseInput('SYNTH'));

        $this->assertContains($result['action'], ['WAIT', 'NO_TRADE']);
        $this->assertNotSame('decision_ready', $result['evidence_readiness']);
        $this->assertNotSame('candidate_ready', $result['action_candidate']['status']);
        $this->assertSame('unavailable', $result['risk']['position_sizing']['status']);
        $this->assertNull($result['trade_plan']['execution_readiness']['reference_quantity']);
    }

    protected function registerGoldenDecisionArtifacts(string $ticker): void
    {
        $this->registerArtifact($ticker, 'trade_episode_dataset', 'trade_episode_dataset_v1', false, true);
        $this->registerArtifact($ticker, 'tp_optimizer', 'tp_optimizer_v1', true, true, ['selected_value' => 5.0]);
        $this->registerArtifact($ticker, 'sl_optimizer', 'sl_optimizer_v1_1', true, true, ['selected_value' => 2.0]);
    }

    protected function registerResearchOnlyArtifacts(string $ticker): void
    {
        $this->registerArtifact($ticker, 'trade_episode_dataset', 'trade_episode_dataset_v1', false, false);
        $this->registerArtifact($ticker, 'tp_optimizer', 'tp_optimizer_v1', false, false);
        $this->registerArtifact($ticker, 'sl_optimizer', 'sl_optimizer_v1_1', false, false);
    }

    protected function registerArtifact(string $ticker, string $type, string $schema, bool $selected, bool $decisionUsable, array $summary = []): TradeResearchArtifact
    {
        $payload = [
            'schema_version' => $schema,
            'artifact_type' => $type,
            'ticker' => $ticker,
            'generated_at' => '2026-07-01T09:30:00+07:00',
            'generator_version' => 'vertical_slice_test_v1',
            'quality' => [
                'status' => 'valid',
                'usable_for_research' => true,
                'usable_for_decision' => $decisionUsable,
                'event_count' => 12,
                'episode_count' => 12,
            ],
            'source' => [
                'data_start' => '2026-01-01',
                'data_end' => '2026-06-30',
            ],
            'summary' => array_replace(['diagnostic_fixture' => true], $summary),
        ];

        if ($selected) {
            $payload['selected'] = ['value' => $summary['selected_value'] ?? 1.0, 'unit' => 'percent'];
        }

        $path = $this->artifactRoot.'/'.strtolower($ticker).'_'.$type.'.json';
        File::put($path, json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

        $result = app(ResearchArtifactRegistryService::class)->register($path, verifyDependencies: true);

        $this->assertSame('imported', $result['status'], json_encode($result['validation'] ?? [], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        $artifact = $result['artifact'];
        $this->assertSame('valid', $artifact->validation_status);
        $this->assertFalse($artifact->is_stale);
        $this->assertFalse($artifact->is_quarantined);
        $this->assertSame($decisionUsable && $selected, (bool) app(ResearchArtifactRegistryService::class)->latestDecisionUsable($ticker, $type));
        $this->assertTrue($artifact->dependencies->every(fn ($dependency) => $dependency->resolution_status === 'resolved'));

        return $artifact;
    }

    protected function baseInput(string $ticker): array
    {
        return [
            'ticker' => $ticker,
            'decision_at' => '2026-07-01T10:00:00+07:00',
            'prediction' => [
                'available' => true,
                'variant' => strtolower($ticker).'_technical',
                'semantic_role' => 'directional',
                'predicted_value' => 'up',
                'probability' => 0.72,
                'generated_at' => '2026-07-01T09:55:00+07:00',
                'schema_version' => 'synthetic_prediction_v1',
                'source_identifier' => 'vertical-slice-fixture',
            ],
            'market_context' => ['current_price' => 100.0, 'market_open' => true, 'data_timestamp' => '2026-07-01T09:59:00+07:00'],
            'open_trade' => null,
        ];
    }

    protected function goldenInput(string $ticker, array $candidate): array
    {
        return array_replace($this->baseInput($ticker), [
            'selected_parameters' => $this->selectedParameters($ticker, $candidate),
            'entry_reference' => $this->entryReference($ticker, $candidate),
            'capital_context' => $this->capitalContext(),
            'capital_risk_policy' => $this->capitalPolicy($candidate),
            'market_constraints' => $this->marketConstraints($ticker, $candidate),
            'execution_cash_context' => $this->cashContext($candidate, 600000.0),
            'execution_cost_evidence' => ['schema_version' => 'trading_execution_cost_evidence_v1', 'status' => 'reference_only', 'candidate_id' => $candidate['candidate_id'], 'estimated_cost_amount' => 0.0, 'currency' => 'IDR', 'synthetic_test_only' => true],
            'liquidity_evidence' => ['schema_version' => 'trading_liquidity_evidence_v1', 'status' => 'reference_only', 'candidate_id' => $candidate['candidate_id'], 'maximum_reference_units' => null, 'synthetic_test_only' => true],
            'portfolio_context' => $this->portfolioContext(),
            'position_snapshots' => $this->positionSnapshots(),
            'portfolio_risk_policy' => $this->portfolioPolicy($candidate, 5.0),
            'portfolio_approval_policy' => $this->portfolioApprovalPolicy($candidate),
            'portfolio_authorization' => $this->portfolioAuthorization($candidate),
        ]);
    }

    protected function selectedParameters(string $ticker, array $candidate): array
    {
        return ['schema_version'=>'trading_selected_parameters_v1','ticker'=>$ticker,'candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'decision_usable','take_profit'=>['selected'=>true,'parameter_type'=>'percentage','value'=>5.0,'unit'=>'percent','source_artifact'=>$this->parameterSource('tp_optimizer', 1)],'stop_loss'=>['selected'=>true,'parameter_type'=>'percentage','value'=>2.0,'unit'=>'percent','source_artifact'=>$this->parameterSource('sl_optimizer', 2)],'generated_at'=>'2026-07-01T09:55:00+07:00','synthetic_test_only'=>true];
    }

    protected function parameterSource(string $type, int $id): array
    {
        return ['artifact_type'=>$type,'registry_artifact_id'=>$id,'schema_version'=>$type.'_v1','checksum'=>str_repeat((string) $id, 64),'usage_tier'=>'decision_usable','quality_grade'=>'healthy','usable_for_decision'=>true,'selected_available'=>true,'is_stale'=>false,'is_quarantined'=>false,'dependency_status'=>['resolved']];
    }

    protected function entryReference(string $ticker, array $candidate): array
    {
        return ['schema_version'=>'trading_entry_reference_v1','ticker'=>$ticker,'candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'status'=>'reference_only','price'=>100.0,'currency'=>'IDR','price_type'=>'reference_market_price','observed_at'=>'2026-07-01T09:59:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'fixture-entry-100'],'executable'=>false,'synthetic_test_only'=>true];
    }

    protected function capitalContext(): array
    {
        return ['schema_version'=>'trading_capital_context_v1','status'=>'reference_only','capital_scope'=>'single_candidate_reference','capital_base'=>['amount'=>1000000.0,'currency'=>'IDR'],'available_cash'=>null,'reserved_capital'=>null,'current_exposure'=>null,'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'capital-fixture-1m'],'approved_for_execution'=>false,'synthetic_test_only'=>true,'warnings'=>[]];
    }

    protected function capitalPolicy(array $candidate): array
    {
        return ['schema_version'=>'trading_capital_risk_policy_v1','status'=>'reference_only','method'=>'fixed_fractional','maximum_loss_pct'=>1.0,'maximum_loss_amount'=>null,'currency'=>'IDR','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'policy_version'=>'fixed_fractional_reference_v1','source'=>['type'=>'synthetic_test_fixture','identifier'=>'capital-policy'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function marketConstraints(string $ticker, array $candidate): array
    {
        return ['schema_version'=>'trading_market_constraints_v1','status'=>'reference_only','ticker'=>$ticker,'candidate_id'=>$candidate['candidate_id'],'market'=>'synthetic','currency'=>'IDR','unit_step'=>100,'minimum_order_units'=>100,'maximum_order_units'=>null,'price_step'=>null,'minimum_notional'=>null,'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'market-constraint-1'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function cashContext(array $candidate, float $amount): array
    {
        return ['schema_version'=>'trading_execution_cash_context_v1','status'=>'reference_only','candidate_id'=>$candidate['candidate_id'],'currency'=>'IDR','available_cash'=>$amount,'reserved_cash'=>null,'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'cash-fixture'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function portfolioContext(): array
    {
        return ['schema_version'=>'trading_portfolio_context_v1','status'=>'reference_only','portfolio_id'=>'synthetic-portfolio-1','base_currency'=>'IDR','capital_base'=>10000000.0,'available_cash'=>null,'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'portfolio-context'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function positionSnapshots(): array
    {
        return [['schema_version'=>'trading_position_snapshot_v1','status'=>'reference_only','position_id'=>'existing-1','portfolio_id'=>'synthetic-portfolio-1','ticker'=>'OTHER','sector'=>'energy','currency'=>'IDR','side'=>'long','quantity'=>10000,'reference_price'=>200.0,'reference_notional'=>2000000.0,'capital_at_risk'=>200000.0,'risk_source'=>['type'=>'explicit_reference_input','identifier'=>'existing-risk'],'as_of'=>'2026-07-01T10:00:00+07:00','source'=>['type'=>'synthetic_test_fixture','identifier'=>'position-existing'],'approved_for_execution'=>false,'synthetic_test_only'=>true]];
    }

    protected function portfolioPolicy(array $candidate, float $maxExposurePct): array
    {
        return ['schema_version'=>'trading_portfolio_risk_policy_v1','status'=>'reference_only','portfolio_id'=>'synthetic-portfolio-1','policy_id'=>'portfolio-policy-synth','policy_version'=>'v1','candidate_id'=>$candidate['candidate_id'],'candidate_intent'=>$candidate['intent'],'limits'=>['maximum_aggregate_capital_at_risk_pct'=>$maxExposurePct,'maximum_single_ticker_notional_pct'=>25.0,'maximum_single_ticker_capital_at_risk_pct'=>2.0],'source'=>['type'=>'synthetic_test_fixture','identifier'=>'portfolio-policy'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function portfolioApprovalPolicy(array $candidate): array
    {
        return ['schema_version'=>'trading_portfolio_approval_policy_v1','status'=>'reference_only','policy_id'=>'approval-policy-synth','policy_version'=>'v1','portfolio_id'=>'synthetic-portfolio-1','candidate_id'=>$candidate['candidate_id'],'requirements'=>['portfolio_risk_evaluated'=>true,'portfolio_limits_passed'=>true,'authorization_required'=>false],'source'=>['type'=>'synthetic_test_fixture','identifier'=>'approval-policy'],'approved_for_execution'=>false,'synthetic_test_only'=>true];
    }

    protected function portfolioAuthorization(array $candidate): array
    {
        return ['schema_version'=>'trading_portfolio_authorization_v1','status'=>'reference_only','authorization_id'=>'authorization-synth','portfolio_id'=>'synthetic-portfolio-1','candidate_id'=>$candidate['candidate_id'],'authorization_decision'=>'not_required','authorized_for_reference_approval'=>true,'authorized_for_production'=>false,'authorized_for_execution'=>false,'source'=>['type'=>'synthetic_test_fixture','identifier'=>'authorization'],'synthetic_test_only'=>true];
    }
}
