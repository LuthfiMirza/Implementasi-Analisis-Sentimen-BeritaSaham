<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SentimentManualLabel extends Model
{
    public const LABELS = ['positive', 'neutral', 'negative'];

    public const SAMPLE_METHODS = ['legacy_hard_case', 'representative_random'];

    protected $fillable = [
        'news_article_id',
        'user_id',
        'label',
        'sample_method',
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
