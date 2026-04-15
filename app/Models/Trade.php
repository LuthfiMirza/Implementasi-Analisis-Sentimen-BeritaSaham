<?php

namespace App\Models;

use Carbon\Carbon;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Trade extends Model
{
    protected $fillable = [
        'user_id', 'stock_id', 'signal_quality',
        'entry_price', 'entry_zone_low', 'entry_zone_high',
        'stop_loss', 'target_1', 'target_2', 'rr_ratio',
        'lot_size', 'position_value',
        'dss_score', 'dss_status', 'dss_prediction',
        'dss_confidence', 'sentiment_avg', 'indicators_snapshot',
        'status', 'entry_date', 'exit_date', 'exit_price',
        'holding_days', 'result', 'pnl_per_share',
        'pnl_total', 'pnl_percent', 'actual_rr', 'notes',
    ];

    protected $casts = [
        'entry_date' => 'date',
        'exit_date' => 'date',
        'indicators_snapshot' => 'array',
        'entry_price' => 'float',
        'stop_loss' => 'float',
        'target_1' => 'float',
        'target_2' => 'float',
        'exit_price' => 'float',
        'pnl_total' => 'float',
        'pnl_percent' => 'float',
        'rr_ratio' => 'float',
        'actual_rr' => 'float',
        'dss_score' => 'float',
        'dss_confidence' => 'float',
    ];

    public function stock(): BelongsTo
    {
        return $this->belongsTo(Stock::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function close(float $exitPrice, string $result): void
    {
        $pnlPerShare = $exitPrice - $this->entry_price;
        $pnlTotal = $pnlPerShare * ($this->lot_size ?? 1);
        $pnlPct = $this->entry_price > 0
            ? round(($pnlPerShare / $this->entry_price) * 100, 2)
            : 0;
        $risk = $this->entry_price - $this->stop_loss;
        $actualRR = $risk > 0 ? round($pnlPerShare / $risk, 2) : 0;
        $holdingDays = $this->entry_date ? $this->entry_date->diffInDays(Carbon::now()) : null;

        $this->update([
            'exit_price' => $exitPrice,
            'exit_date' => Carbon::now()->toDateString(),
            'result' => $result,
            'status' => 'closed',
            'pnl_per_share' => round($pnlPerShare, 2),
            'pnl_total' => round($pnlTotal, 2),
            'pnl_percent' => $pnlPct,
            'actual_rr' => $actualRR,
            'holding_days' => $holdingDays,
        ]);
    }

    public function resultColor(): string
    {
        return match ($this->result) {
            'hit_target_1', 'hit_target_2' => 'green',
            'stop_loss' => 'red',
            'manual_close' => 'yellow',
            default => 'blue',
        };
    }
}
