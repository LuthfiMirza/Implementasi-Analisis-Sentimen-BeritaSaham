<?php

namespace Tests\Feature;

use Tests\TestCase;

class AdminStockFundamentalTest extends TestCase
{
    public function test_guest_cannot_update_stock_fundamental(): void
    {
        $stock = $this->seedStock('DEWA');

        $this->patch(route('admin.stocks.fundamental.update', $stock), [
            'fundamentals_updated_at' => '2026-06-22',
        ])->assertRedirect('/login');
    }

    public function test_admin_can_update_only_fundamental_columns(): void
    {
        $stock = $this->seedStock('DEWA', [
            'company_name' => 'Darma Henwa Tbk',
            'pbv' => 1.0,
            'per' => 7.8,
            'roe' => 13.1,
            'der' => 0.9,
            'eps' => 10.0,
            'dividend_yield' => 1.2,
            'fundamentals_updated_at' => '2025-12-31',
        ]);

        $this->actingAsAdmin()
            ->patch(route('admin.stocks.fundamental.update', $stock), [
                'pbv' => '1.25',
                'per' => '8.50',
                'roe' => '14.75',
                'der' => '0.80',
                'eps' => '12.30',
                'dividend_yield' => '1.60',
                'fundamentals_updated_at' => '2026-06-22',
            ])
            ->assertRedirect(route('admin.stocks.edit', $stock));

        $stock->refresh();

        $this->assertSame('Darma Henwa Tbk', $stock->company_name);
        $this->assertEquals(1.25, $stock->pbv);
        $this->assertEquals(8.5, $stock->per);
        $this->assertEquals(14.75, $stock->roe);
        $this->assertEquals(0.8, $stock->der);
        $this->assertEquals(12.3, $stock->eps);
        $this->assertEquals(1.6, $stock->dividend_yield);
        $this->assertSame('2026-06-22', $stock->fundamentals_updated_at->toDateString());
    }

    public function test_fundamental_update_rejects_non_numeric_values(): void
    {
        $stock = $this->seedStock('DEWA');

        $this->actingAsAdmin()
            ->from(route('admin.stocks.edit', $stock))
            ->patch(route('admin.stocks.fundamental.update', $stock), [
                'pbv' => 'not-a-number',
                'fundamentals_updated_at' => '2026-06-22',
            ])
            ->assertRedirect(route('admin.stocks.edit', $stock))
            ->assertSessionHasErrors('pbv');
    }
}
