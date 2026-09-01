<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/**
 * Monthly KSEI securities-ownership snapshot per stock (see create_ksei_ownerships_table).
 * Aggregate local/foreign composition -- not individual shareholders.
 */
class KseiOwnership extends Model
{
    protected $fillable = [
        'snapshot_date', 'stock_code', 'stock_name',
        'total_shares', 'local_shares', 'foreign_shares',
        'local_pct', 'foreign_pct', 'foreign_pct_delta',
        'breakdown', 'source',
    ];

    protected $casts = [
        'snapshot_date' => 'date',
        'total_shares' => 'integer',
        'local_shares' => 'integer',
        'foreign_shares' => 'integer',
        'local_pct' => 'float',
        'foreign_pct' => 'float',
        'foreign_pct_delta' => 'float',
        'breakdown' => 'array',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class, 'stock_code', 'code');
    }
}
