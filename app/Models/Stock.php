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
        'logo_url',
        'sector',
        'description',
        'exchange',
        'tradingview_symbol',
        'yahoo_symbol',
        'is_active',
        'pbv',
        'per',
        'roe',
        'der',
        'eps',
        'book_value_per_share',
        'dividend_yield',
        'fundamentals_updated_at',
    ];

    protected $casts = [
        'pbv' => 'float',
        'per' => 'float',
        'roe' => 'float',
        'der' => 'float',
        'eps' => 'float',
        'book_value_per_share' => 'float',
        'dividend_yield' => 'float',
        'fundamentals_updated_at' => 'date',
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
