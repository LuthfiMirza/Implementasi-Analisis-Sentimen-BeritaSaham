<?php

namespace Database\Factories;

use App\Models\FetchLog;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<FetchLog>
 */
class FetchLogFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'source_name' => fake()->randomElement(['mock', 'rss', 'manual']),
            'status' => fake()->randomElement(['success', 'warning', 'failed']),
            'message' => fake()->sentence(),
            'records_count' => fake()->numberBetween(0, 50),
            'ran_at' => now(),
        ];
    }
}
