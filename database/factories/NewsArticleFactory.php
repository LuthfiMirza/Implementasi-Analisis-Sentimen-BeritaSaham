<?php

namespace Database\Factories;

use App\Models\NewsArticle;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<NewsArticle>
 */
class NewsArticleFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'title' => fake()->sentence(8),
            'slug' => fake()->unique()->slug(),
            'source_url' => fake()->url(),
            'source_provider' => 'rss_local',
            'published_at' => fake()->dateTimeBetween('-14 days', 'now'),
            'summary' => fake()->sentence(15),
            'content_snippet' => fake()->paragraph(),
            'full_text' => fake()->paragraphs(3, true),
            'sentiment_label' => fake()->randomElement(['positive', 'neutral', 'negative']),
            'sentiment_score' => fake()->randomFloat(2, -1, 1),
            'sentiment_confidence' => fake()->randomFloat(2, 0.4, 0.95),
            'sentiment_method' => 'rule_based',
            'sentiment_meta' => [
                'matched_positive_terms' => ['demo'],
                'matched_negative_terms' => [],
                'reason_summary' => 'factory seeded',
            ],
            'analyzed_at' => now(),
            'language' => 'id',
            'raw_payload' => ['seeded' => true],
            'fetched_at' => now(),
        ];
    }
}
