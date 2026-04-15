<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Builder;
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
        'relevance_score',
        'relevance_band',
        'source_provider',
        'source_weight',
        'matched_keywords',
        'detected_language',
        'entity_match_score',
        'market_context_score',
        'language_score',
        'final_quality_score',
        'quality_band',
        'quality_flags',
    ];

    protected $casts = [
        'published_at' => 'datetime',
        'fetched_at' => 'datetime',
        'sentiment_score' => 'float',
        'sentiment_confidence' => 'float',
        'raw_payload' => 'array',
        'sentiment_meta' => 'array',
        'analyzed_at' => 'datetime',
        'relevance_score' => 'float',
        'source_weight' => 'float',
        'matched_keywords' => 'array',
        'entity_match_score' => 'float',
        'market_context_score' => 'float',
        'language_score' => 'float',
        'final_quality_score' => 'float',
        'quality_flags' => 'array',
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

    public function scopeForStockContext(Builder $query, Stock|int|null $stock, bool $includeMacro = true): Builder
    {
        $stockId = $stock instanceof Stock ? $stock->id : $stock;
        $macroProviders = (array) config('news.macro_global_providers', ['ojk_rss']);

        if (! $includeMacro) {
            return $stockId !== null
                ? $query->where('stock_id', $stockId)
                : $query->whereRaw('1 = 0');
        }

        return $query->where(function (Builder $builder) use ($stockId, $macroProviders) {
            if ($stockId !== null) {
                $builder->where('stock_id', $stockId)
                    ->orWhere(function (Builder $macro) use ($macroProviders) {
                        $macro->whereNull('stock_id')
                            ->whereIn('source_provider', $macroProviders);
                    });

                return;
            }

            $builder->whereNull('stock_id')
                ->whereIn('source_provider', $macroProviders);
        });
    }
}
