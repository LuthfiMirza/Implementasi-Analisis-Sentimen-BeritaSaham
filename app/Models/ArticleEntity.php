<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Factories\HasFactory;

class ArticleEntity extends Model
{
    use HasFactory;

    protected $fillable = [
        'news_article_id',
        'entity_name',
        'entity_type',
        'relevance_score',
    ];

    protected $casts = [
        'relevance_score' => 'float',
    ];

    public function article()
    {
        return $this->belongsTo(NewsArticle::class, 'news_article_id');
    }
}
