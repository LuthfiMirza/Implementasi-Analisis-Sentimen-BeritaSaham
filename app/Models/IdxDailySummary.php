<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/**
 * One IDX end-of-day stock-summary row (see the create_idx_daily_summaries_table migration).
 * Read-heavy: written once/day by `idx:fetch-daily-summary`, read by IdxMarketSummaryService.
 */
class IdxDailySummary extends Model
{
    protected $fillable = [
        'trade_date', 'stock_code', 'stock_name', 'remarks',
        'previous', 'open', 'high', 'low', 'close', 'change', 'pct_change',
        'volume', 'value', 'frequency',
        'foreign_buy', 'foreign_sell', 'foreign_net', 'foreign_net_value',
        'listed_shares', 'source',
    ];

    protected $casts = [
        'trade_date' => 'date',
        'previous' => 'float',
        'open' => 'float',
        'high' => 'float',
        'low' => 'float',
        'close' => 'float',
        'change' => 'float',
        'pct_change' => 'float',
        'volume' => 'integer',
        'value' => 'float',
        'frequency' => 'integer',
        'foreign_buy' => 'integer',
        'foreign_sell' => 'integer',
        'foreign_net' => 'integer',
        'foreign_net_value' => 'float',
        'listed_shares' => 'integer',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class, 'stock_code', 'code');
    }
}
