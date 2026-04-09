<?php

namespace App\Services\Sentiment;

use App\Models\NewsArticle;
use Illuminate\Support\Collection;

class SentimentSummaryService
{
    public function summarize(Collection $articles): array
    {
        $totals = [
            'positive' => 0,
            'neutral' => 0,
            'negative' => 0,
        ];
        $scores = [];

        /** @var NewsArticle $article */
        foreach ($articles as $article) {
            $label = $article->sentiment_label ?? 'neutral';
            $totals[$label] = ($totals[$label] ?? 0) + 1;
            $scores[] = (float) ($article->sentiment_score ?? 0);
        }

        $totalCount = array_sum($totals) ?: 1;
        $average = count($scores) ? array_sum($scores) / count($scores) : 0;

        return [
            'total' => $totalCount,
            'positive' => $totals['positive'] ?? 0,
            'neutral' => $totals['neutral'] ?? 0,
            'negative' => $totals['negative'] ?? 0,
            'positive_pct' => round(($totals['positive'] ?? 0) / $totalCount * 100, 1),
            'neutral_pct' => round(($totals['neutral'] ?? 0) / $totalCount * 100, 1),
            'negative_pct' => round(($totals['negative'] ?? 0) / $totalCount * 100, 1),
            'average_score' => round($average, 2),
            'top_positive' => $articles->where('sentiment_label', 'positive')->sortByDesc('sentiment_score')->first(),
            'top_negative' => $articles->where('sentiment_label', 'negative')->sortBy('sentiment_score')->first(),
        ];
    }

    public function generateInsight(string $stockCode, array $summary, ?float $priceChange = null): string
    {
        $direction = $summary['average_score'] > 0.15 ? 'positif' : ($summary['average_score'] < -0.15 ? 'negatif' : 'netral');
        $pricePhrase = $priceChange !== null ? "Perubahan harga terakhir sekitar ".number_format($priceChange, 2)."%" : 'Harga terkini belum tersinkron';

        return sprintf(
            'Sentimen berita %s cenderung %s dengan %s%% artikel positif, %s%% netral, dan %s%% negatif. %s.',
            $stockCode,
            $direction,
            $summary['positive_pct'],
            $summary['neutral_pct'],
            $summary['negative_pct'],
            $pricePhrase
        );
    }

    public function distributionByDate(Collection $articles): array
    {
        return $articles
            ->groupBy(fn (NewsArticle $article) => optional($article->published_at)->toDateString() ?? now()->toDateString())
            ->map(fn ($group) => [
                'count' => $group->count(),
                'avg_score' => round($group->avg('sentiment_score'), 2),
            ])
            ->sortKeys()
            ->toArray();
    }
}
