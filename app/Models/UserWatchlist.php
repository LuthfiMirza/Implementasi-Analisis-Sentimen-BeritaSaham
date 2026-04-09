<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class UserWatchlist extends Model
{
    protected $fillable = [
        'user_id',
        'stock_id',
    ];

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function stock()
    {
        return $this->belongsTo(Stock::class);
    }
}
