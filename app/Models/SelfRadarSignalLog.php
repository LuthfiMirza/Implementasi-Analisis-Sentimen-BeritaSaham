<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SelfRadarSignalLog extends Model
{
    protected $fillable = [
        'ticker', 'signal_date', 'rank', 'price_at_first_seen', 'latest_price', 'rsi14',
        'ret_5d_pct', 'dd_20d_pct', 'score', 'first_seen_at', 'last_seen_at',
        'entry_window_start_at', 'entry_window_end_at', 'trailing_start_at', 'fill_price',
        'filled_at', 'exit_price', 'exited_at', 'result', 'pnl_pct',
    ];

    protected $casts = [
        'signal_date' => 'date',
        'first_seen_at' => 'datetime',
        'last_seen_at' => 'datetime',
        'entry_window_start_at' => 'datetime',
        'entry_window_end_at' => 'datetime',
        'trailing_start_at' => 'datetime',
        'filled_at' => 'datetime',
        'exited_at' => 'datetime',
    ];
}
