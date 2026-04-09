<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class StockPrice extends Model
{
    /** @use HasFactory<\Database\Factories\StockPriceFactory> */
    use HasFactory;

    protected $fillable = [
        'stock_id',
        'price_date',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'source',
        'interval_type',
    ];

    protected $casts = [
        'price_date' => 'datetime',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class);
    }
}
