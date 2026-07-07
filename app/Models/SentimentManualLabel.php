<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SentimentManualLabel extends Model
{
    public const LABELS = ['positive', 'neutral', 'negative'];

    protected $fillable = [
        'news_article_id',
        'user_id',
        'label',
    ];

    public function article()
    {
        return $this->belongsTo(NewsArticle::class, 'news_article_id');
    }

    public function user()
    {
        return $this->belongsTo(User::class);
    }
}
