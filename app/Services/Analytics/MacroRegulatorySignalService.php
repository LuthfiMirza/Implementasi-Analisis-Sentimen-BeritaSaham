<?php

namespace App\Services\Analytics;

use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Support\Collection;

class MacroRegulatorySignalService
{
    public function evaluate(
        Collection $articles,
        int $periodDays = 30,
        CarbonInterface|string|null $referenceDate = null,
        ?bool $enabled = null
    ): array {
        $isEnabled = $enabled ?? (bool) config('analytics.macro_regulatory_signal.enabled', true);
        $referencePoint = $this->resolveReferenceDate($referenceDate, $articles);

        if (! $isEnabled) {
            return $this->disabledPayload($referencePoint, 'Feature flag dimatikan.');
        }

        $providers = (array) config('analytics.macro_regulatory_signal.providers', ['ojk_rss']);
        $periodStart = $referencePoint->copy()->subDays(max(1, $periodDays));

        $articlesInPeriod = $articles
            ->filter(function ($article) use ($periodStart, $referencePoint) {
                if (! $article->published_at) {
                    return false;
                }

                $published = $article->published_at instanceof CarbonInterface
                    ? $article->published_at->copy()
                    : Carbon::parse($article->published_at);

                return $published->greaterThanOrEqualTo($periodStart)
                    && $published->lessThanOrEqualTo($referencePoint);
            })
            ->values();

        $macroArticles = $articlesInPeriod
            ->filter(function ($article) use ($providers) {
                return is_null($article->stock_id)
                    && in_array((string) $article->source_provider, $providers, true);
            })
            ->values();

        if ($macroArticles->isEmpty()) {
            return array_merge(
                $this->disabledPayload($referencePoint, 'Tidak ada artikel regulasi makro pada window ini.'),
                [
                    'enabled' => true,
                    'active' => false,
                ]
            );
        }

        $macroCount = $macroArticles->count();
        $neutralCount = $macroArticles->where('sentiment_label', 'neutral')->count();
        $neutralShare = $macroCount > 0 ? round($neutralCount / $macroCount, 3) : 0.0;
        $articleShare = $articlesInPeriod->count() > 0 ? round($macroCount / $articlesInPeriod->count(), 3) : 0.0;
        $averageQuality = round((float) ($macroArticles->avg('final_quality_score') ?? 0), 3);

        $recent3 = $macroArticles->filter(fn ($article) => $this->publishedWithinDays($article, $referencePoint, 3))->count();
        $recent7 = $macroArticles->filter(fn ($article) => $this->publishedWithinDays($article, $referencePoint, 7))->count();

        $spikeScore = min(1.0, ($recent3 * 0.45) + ($recent7 * 0.18) + ($articleShare * 0.55));
        $coverageScore = min(1.0, $macroCount / 4);
        $qualityScore = min(1.0, max(0.0, $averageQuality));
        $intensity = round(min(1.0, ($spikeScore * 0.65) + ($coverageScore * 0.25) + ($qualityScore * 0.10)), 3);

        $watchCount = (int) config('analytics.macro_regulatory_signal.watch_recent_7d_count', 2);
        $overhangCount = (int) config('analytics.macro_regulatory_signal.overhang_recent_3d_count', 2);
        $neutralThreshold = (float) config('analytics.macro_regulatory_signal.neutral_share_threshold', 0.7);

        $attentionRegime = 'normal';
        if ($recent3 >= $overhangCount || $intensity >= 0.75) {
            $attentionRegime = 'regulatory_overhang';
        } elseif ($recent7 >= $watchCount || $intensity >= 0.35) {
            $attentionRegime = 'regulatory_watch';
        }

        $cautionFlag = $attentionRegime !== 'normal' && $neutralShare >= $neutralThreshold;

        $confidencePenaltyScale = (float) config('analytics.macro_regulatory_signal.confidence_penalty_scale', 0.28);
        $scorePenaltyScale = (float) config('analytics.macro_regulatory_signal.score_penalty_scale', 0.18);
        $thresholdScale = (float) config('analytics.macro_regulatory_signal.threshold_tightening_scale', 0.12);
        $confidenceMultiplier = $cautionFlag
            ? round(max((float) config('analytics.macro_regulatory_signal.min_confidence_multiplier', 0.7), 1 - ($intensity * $confidencePenaltyScale)), 3)
            : 1.0;
        $scoreMultiplier = $cautionFlag
            ? round(max((float) config('analytics.macro_regulatory_signal.min_score_multiplier', 0.82), 1 - ($intensity * $scorePenaltyScale)), 3)
            : 1.0;
        $thresholdTightening = $cautionFlag ? round(1 + ($intensity * $thresholdScale), 3) : 1.0;

        $headlineSample = $macroArticles
            ->sortByDesc('published_at')
            ->take(3)
            ->pluck('title')
            ->filter()
            ->values()
            ->all();

        $narrative = $cautionFlag
            ? sprintf(
                'Regulatory %s: %d artikel OJK makro (%d netral) pada %d hari terakhir. Confidence directional dimoderasi, bukan diarahkan ulang.',
                $attentionRegime,
                $macroCount,
                $neutralCount,
                $periodDays
            )
            : sprintf(
                'Ada %d artikel OJK makro pada window %d hari, tetapi intensitasnya belum cukup untuk moderasi confidence.',
                $macroCount,
                $periodDays
            );

        return [
            'enabled' => true,
            'active' => true,
            'reference_date' => $referencePoint->toDateString(),
            'period_days' => $periodDays,
            'article_count' => $macroCount,
            'neutral_article_count' => $neutralCount,
            'neutral_share' => $neutralShare,
            'article_share' => $articleShare,
            'average_quality' => $averageQuality,
            'recent_3d_count' => $recent3,
            'recent_7d_count' => $recent7,
            'attention_regime' => $attentionRegime,
            'caution_flag' => $cautionFlag,
            'context_score' => $intensity,
            'macro_policy_attention_score' => $intensity,
            'confidence_multiplier' => $confidenceMultiplier,
            'score_multiplier' => $scoreMultiplier,
            'threshold_tightening_factor' => $thresholdTightening,
            'directional_bias' => 0.0,
            'headline_sample' => $headlineSample,
            'narrative' => $narrative,
        ];
    }

    protected function resolveReferenceDate(
        CarbonInterface|string|null $referenceDate,
        Collection $articles
    ): CarbonInterface {
        if ($referenceDate instanceof CarbonInterface) {
            return $referenceDate;
        }

        if (is_string($referenceDate) && trim($referenceDate) !== '') {
            return Carbon::parse($referenceDate);
        }

        $lastArticleDate = $articles
            ->pluck('published_at')
            ->filter()
            ->map(fn ($date) => $date instanceof CarbonInterface ? $date : Carbon::parse($date))
            ->sort()
            ->last();

        return $lastArticleDate ?: now();
    }

    protected function publishedWithinDays($article, CarbonInterface $referencePoint, int $days): bool
    {
        if (! $article->published_at) {
            return false;
        }

        $published = $article->published_at instanceof CarbonInterface
            ? $article->published_at->copy()
            : Carbon::parse($article->published_at);

        return $published->greaterThanOrEqualTo($referencePoint->copy()->subDays($days))
            && $published->lessThanOrEqualTo($referencePoint);
    }

    protected function disabledPayload(CarbonInterface $referencePoint, string $reason): array
    {
        return [
            'enabled' => false,
            'active' => false,
            'reference_date' => $referencePoint->toDateString(),
            'period_days' => 0,
            'article_count' => 0,
            'neutral_article_count' => 0,
            'neutral_share' => 0.0,
            'article_share' => 0.0,
            'average_quality' => 0.0,
            'recent_3d_count' => 0,
            'recent_7d_count' => 0,
            'attention_regime' => 'disabled',
            'caution_flag' => false,
            'context_score' => 0.0,
            'macro_policy_attention_score' => 0.0,
            'confidence_multiplier' => 1.0,
            'score_multiplier' => 1.0,
            'threshold_tightening_factor' => 1.0,
            'directional_bias' => 0.0,
            'headline_sample' => [],
            'narrative' => $reason,
        ];
    }
}
