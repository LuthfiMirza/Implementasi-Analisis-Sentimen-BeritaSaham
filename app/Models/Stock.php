<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Stock extends Model
{
    /** @use HasFactory<\Database\Factories\StockFactory> */
    use HasFactory;

    protected $fillable = [
        'code',
        'company_name',
        'sector',
        'description',
        'exchange',
        'tradingview_symbol',
        'yahoo_symbol',
        'is_active',
    ];

    public function aliases()
    {
        return $this->hasMany(StockAlias::class);
    }

    public function prices()
    {
        return $this->hasMany(StockPrice::class);
    }

    public function latestPrice()
    {
        return $this->hasOne(StockPrice::class)->latestOfMany('price_date');
    }

    public function newsArticles()
    {
        return $this->hasMany(NewsArticle::class);
    }

    public function watchlists()
    {
        return $this->hasMany(UserWatchlist::class);
    }
}
