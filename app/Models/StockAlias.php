<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class StockAlias extends Model
{
    /** @use HasFactory<\Database\Factories\StockAliasFactory> */
    use HasFactory;

    protected $fillable = [
        'stock_id',
        'alias_name',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class);
    }
}
