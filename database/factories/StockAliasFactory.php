<?php

namespace Database\Factories;

use App\Models\StockAlias;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<StockAlias>
 */
class StockAliasFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'alias_name' => fake()->companySuffix(),
        ];
    }
}
