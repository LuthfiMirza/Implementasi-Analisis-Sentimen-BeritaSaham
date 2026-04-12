<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\StockKeywordMapper;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class StockKeywordMapperExclusionTest extends TestCase
{
    use RefreshDatabase;

    public function test_global_exclusions_are_applied(): void
    {
        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $mapper = new StockKeywordMapper();

        $exclusions = $mapper->exclusionKeywords($stock);

        $this->assertContains('promo', $exclusions);
        $this->assertContains('diskon', $exclusions);
    }
}
