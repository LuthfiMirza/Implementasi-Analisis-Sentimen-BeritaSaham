<?php

namespace Database\Factories;

use App\Models\Stock;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Stock>
 */
class StockFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        $code = strtoupper(fake()->lexify('????'));
        $close = fake()->randomFloat(2, 100, 5000);

        return [
            'code' => $code,
            'company_name' => fake()->company(),
            'sector' => fake()->randomElement(['Perbankan', 'Teknologi', 'Konsumsi', 'Energi', 'Transportasi']),
            'description' => fake()->sentence(10),
            'exchange' => 'IDX',
            'tradingview_symbol' => 'IDX:'.$code,
            'yahoo_symbol' => $code.'.JK',
            'is_active' => true,
        ];
    }
}
