<?php

namespace Database\Factories;

use App\Models\Stock;
use App\Models\Trade;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Trade>
 */
class TradeFactory extends Factory
{
    protected $model = Trade::class;

    public function definition(): array
    {
        $ticker = fake()->randomElement(['BBCA', 'BBRI', 'TLKM', 'ASII', 'GOTO']);
        $entryPrice = fake()->randomFloat(2, 1000, 9000);
        $quantity = fake()->numberBetween(1, 100);
        $direction = fake()->randomElement(['long', 'short']);

        return [
            'user_id' => User::factory(),
            'stock_id' => Stock::factory(),
            'ticker' => $ticker,
            'direction' => $direction,
            'signal_quality' => 'A',
            'entry_price' => $entryPrice,
            'stop_loss' => $direction === 'long' ? round($entryPrice * 0.95, 2) : round($entryPrice * 1.05, 2),
            'target_1' => $direction === 'long' ? round($entryPrice * 1.1, 2) : round($entryPrice * 0.9, 2),
            'target_2' => $direction === 'long' ? round($entryPrice * 1.2, 2) : round($entryPrice * 0.8, 2),
            'rr_ratio' => 2.0,
            'lot_size' => $quantity,
            'quantity' => $quantity,
            'position_value' => $entryPrice * $quantity,
            'status' => 'open',
            'entry_date' => now()->subDays(3)->toDateString(),
            'trade_date' => now()->subDays(3)->toDateString(),
            'result' => 'open',
            'notes' => 'Factory trade',
        ];
    }

    public function closeState(): static
    {
        return $this->state(function (array $attributes): array {
            $entryPrice = (float) ($attributes['entry_price'] ?? 1000);
            $quantity = (int) ($attributes['quantity'] ?? $attributes['lot_size'] ?? 1);
            $direction = (string) ($attributes['direction'] ?? 'long');
            $exitPrice = $direction === 'long' ? round($entryPrice * 1.05, 2) : round($entryPrice * 0.95, 2);
            $multiplier = $direction === 'short' ? -1 : 1;
            $pnl = ($exitPrice - $entryPrice) * $quantity * $multiplier;

            return [
                'exit_price' => $exitPrice,
                'exit_date' => now()->toDateString(),
                'closed_at' => now(),
                'status' => 'closed',
                'result' => 'manual_close',
                'pnl' => round($pnl, 2),
                'pnl_total' => round($pnl, 2),
            ];
        });
    }
}
