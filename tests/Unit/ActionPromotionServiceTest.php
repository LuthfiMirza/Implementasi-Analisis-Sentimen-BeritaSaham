<?php

namespace Tests\Unit;

use App\Services\Trading\ActionPromotionService;
use Tests\TestCase;

class ActionPromotionServiceTest extends TestCase
{
    public function test_no_selected_candidate_is_not_promoted(): void
    {
        $promotion = (new ActionPromotionService())->promote(['selection'=>$this->selection(null)]);
        $this->assertSame('trading_action_promotion_v1', $promotion['schema_version']);
        $this->assertSame('not_promoted', $promotion['status']);
        $this->assertSame('selected_candidate_required', $promotion['promotion_eligibility']);
        $this->assertNull($promotion['promoted_action']);
        $this->assertNull($promotion['executable_action']);
        $this->assertContains('ACTION_PROMOTION_SELECTED_CANDIDATE_REQUIRED', $promotion['reason_codes']);
    }

    public function test_selected_candidate_still_disabled(): void
    {
        $selected = ['candidate_id'=>'abc','intent'=>'long_entry'];
        $promotion = (new ActionPromotionService())->promote(['selection'=>$this->selection($selected)]);
        $this->assertSame('eligible_but_disabled', $promotion['status']);
        $this->assertSame('eligible_but_disabled', $promotion['promotion_eligibility']);
        $this->assertContains('ACTION_PROMOTION_CAPABILITY_DISABLED', $promotion['reason_codes']);
        $this->assertContains('ACTION_PROMOTION_POLICY_NOT_IMPLEMENTED', $promotion['reason_codes']);
    }

    public function test_reference_ready_trade_plan_is_not_promotable_or_executable(): void
    {
        $selected = ['candidate_id'=>'abc','intent'=>'long_entry'];
        $promotion = (new ActionPromotionService())->promote([
            'selection'=>$this->selection($selected),
            'trade_plan'=>['status'=>'materialized','execution_readiness'=>['status'=>'reference_ready','executable'=>false]],
        ]);

        $this->assertSame('eligible_but_disabled', $promotion['status']);
        $this->assertNull($promotion['promoted_action']);
        $this->assertNull($promotion['executable_action']);
        $this->assertContains('EXECUTION_CAPABILITY_NOT_IMPLEMENTED', $promotion['reason_codes']);
    }

    public function test_validation_rejects_promoted_action(): void
    {
        $service = new ActionPromotionService();
        $promotion = $service->promote(['selection'=>$this->selection(null)]);
        $promotion['promoted_action'] = 'BUY';
        $this->expectException(\InvalidArgumentException::class);
        $service->validatePromotion($promotion);
    }

    protected function selection(?array $selected): array
    {
        return ['safety_action'=>'WAIT','selected_candidate'=>$selected];
    }
}
