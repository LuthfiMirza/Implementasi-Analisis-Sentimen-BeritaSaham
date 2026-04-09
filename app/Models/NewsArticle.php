<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class NewsArticle extends Model
{
    /** @use HasFactory<\Database\Factories\NewsArticleFactory> */
    use HasFactory;

    protected $fillable = [
        'stock_id',
        'news_source_id',
        'title',
        'slug',
        'source_url',
        'published_at',
        'summary',
        'content_snippet',
        'full_text',
        'sentiment_label',
        'sentiment_score',
        'sentiment_confidence',
        'sentiment_method',
        'sentiment_meta',
        'language',
        'raw_payload',
        'fetched_at',
        'analyzed_at',
    ];

    protected $casts = [
        'published_at' => 'datetime',
        'fetched_at' => 'datetime',
        'sentiment_score' => 'float',
        'sentiment_confidence' => 'float',
        'raw_payload' => 'array',
        'sentiment_meta' => 'array',
        'analyzed_at' => 'datetime',
    ];

    public function stock()
    {
        return $this->belongsTo(Stock::class);
    }

    public function source()
    {
        return $this->belongsTo(NewsSource::class, 'news_source_id');
    }

    public function entities()
    {
        return $this->hasMany(ArticleEntity::class);
    }
}
