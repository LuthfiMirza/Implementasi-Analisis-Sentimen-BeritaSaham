<?php

namespace Tests\Feature;

use App\Models\TradeResearchArtifact;
use App\Services\Research\ResearchArtifactDiscoveryService;
use App\Services\Research\ResearchArtifactRegistryService;
use App\Services\Trading\TradingDecisionService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TradingDecisionRegistryIntegrationTest extends TestCase
{
    use RefreshDatabase;

    public function test_current_bumi_and_dewa_registry_state_produces_safe_wait(): void
    {
        $this->importCurrentArtifacts();
        $service = app(TradingDecisionService::class);

        foreach (['BUMI', 'DEWA'] as $ticker) {
            $result = $service->decide($this->input($ticker));
            $this->assertSame('WAIT', $result['action'], $ticker);
            $this->assertSame('safe_downgrade', $result['action_status'], $ticker);
            $this->assertSame('research_only', $result['recommendation_quality'], $ticker);
            $this->assertContains('NO_DECISION_USABLE_TP', $result['reason_codes'], $ticker);
            $this->assertContains('NO_DECISION_USABLE_SL', $result['reason_codes'], $ticker);
            $this->assertSame('trading_confidence_v1_1', $result['confidence']['schema_version']);
            $this->assertSame('research_only', $result['confidence_status']);
            $this->assertNull($result['confidence']['trade_action_confidence']['score']);
            $this->assertSame('trading_risk_v1_3', $result['risk']['schema_version']);
            $this->assertSame('trading_trade_plan_v1_2', $result['trade_plan']['schema_version']);
            $this->assertSame('trading_reference_trade_plan_v1', $result['trade_plan']['reference_plan']['schema_version']);
            $this->assertSame('unavailable', $result['risk']['decision_risk']['status']);
            $this->assertSame('unavailable', $result['trade_plan']['status']);
            $this->assertSame('unavailable', $result['trade_plan']['reference_plan']['status']);
            $this->assertNull($result['risk']['decision_risk']['risk_reward_ratio']);
            $this->assertNull($result['trade_plan']['take_profit']['price']);
            $this->assertNull($result['trade_plan']['stop_loss']['price']);
            $this->assertNull(app(ResearchArtifactRegistryService::class)->latestDecisionUsable($ticker, 'tp_optimizer'));
            $this->assertNull(app(ResearchArtifactRegistryService::class)->latestDecisionUsable($ticker, 'sl_optimizer'));
            $this->assertNull(app(ResearchArtifactRegistryService::class)->latestDecisionUsable($ticker, 'reentry_research'));
        }
    }

    public function test_missing_research_artifacts_produce_no_trade(): void
    {
        $result = app(TradingDecisionService::class)->decide($this->input('BUMI'));

        $this->assertSame('NO_TRADE', $result['action']);
        $this->assertContains('SAFE_DOWNGRADE_NO_TRADE', $result['reason_codes']);
    }

    protected function importCurrentArtifacts(): void
    {
        $root = storage_path('app/trading_research');
        if (! is_dir($root)) {
            $this->markTestSkipped('Current research artifact directory is unavailable.');
        }
        $discovery = app(ResearchArtifactDiscoveryService::class);
        $registry = app(ResearchArtifactRegistryService::class);
        foreach ($discovery->discover($root) as $file) {
            $registry->register($file, verifyDependencies: true);
        }
        $this->assertGreaterThan(0, TradeResearchArtifact::count());
    }

    protected function input(string $ticker): array
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
}
