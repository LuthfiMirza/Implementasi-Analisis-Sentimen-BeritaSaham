<?php

namespace Database\Factories;

use App\Models\NewsSource;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<NewsSource>
 */
class NewsSourceFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => fake()->company().' News',
            'base_url' => fake()->url(),
            'type' => fake()->randomElement(['rss', 'api', 'manual']),
            'is_active' => true,
            'config_json' => ['sample' => true],
        ];
    }
}
