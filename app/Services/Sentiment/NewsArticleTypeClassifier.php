<?php

namespace App\Services\Sentiment;

use App\Models\NewsArticle;

class NewsArticleTypeClassifier
{
    public function classify(NewsArticle $article): string
    {
        if ($article->stock_id === null) {
            return 'macro';
        }

        $text = mb_strtolower(trim(($article->title ?? '').' '.($article->summary ?? '').' '.($article->content_snippet ?? '')));
        if ($this->looksLikeMultiIssuerRecommendation($text)) {
            return 'multi_emiten_recommendation';
        }

        return 'emiten_spesifik';
    }

    private function looksLikeMultiIssuerRecommendation(string $text): bool
    {
        if (! preg_match('/\b(rekomendasi|top pick|pilihan saham|saham pilihan|target harga|watchlist|trading ideas?)\b/u', $text)) {
            return false;
        }

        preg_match_all('/\b[A-Z]{4}\b/u', mb_strtoupper($text), $matches);

        return count(array_unique($matches[0])) >= 2
            || str_contains($text, ' dan ')
            || str_contains($text, ',');
    }
}
