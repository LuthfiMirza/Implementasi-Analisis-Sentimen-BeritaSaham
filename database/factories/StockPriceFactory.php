<?php

namespace Database\Factories;

use App\Models\StockPrice;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<StockPrice>
 */
class StockPriceFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        $open = fake()->randomFloat(2, 100, 2000);
        $close = round($open * fake()->randomFloat(3, 0.95, 1.05), 2);
        $high = max($open, $close) + fake()->randomFloat(2, 0, 10);
        $low = min($open, $close) - fake()->randomFloat(2, 0, 10);

        return [
            'price_date' => fake()->dateTimeBetween('-30 days', 'now'),
            'open' => $open,
            'high' => $high,
            'low' => $low,
            'close' => $close,
            'volume' => fake()->numberBetween(10_000, 10_000_000),
            'source' => 'seed',
            'interval_type' => '1d',
        ];
    }
}
