<?php

namespace App\Services\News;

use App\Models\Stock;
use Illuminate\Support\Str;

class RelevanceScoringService
{
    public function __construct(protected StockKeywordMapper $mapper = new StockKeywordMapper())
    {
    }

    /**
     * Kepercayaan sumber untuk menaikkan final quality jika berasal dari domain tepercaya.
     */
    protected array $trustedDomains = [
        'cnbcindonesia.com' => 0.20,
        'kontan.co.id' => 0.20,
        'bisnis.com' => 0.18,
        'investor.id' => 0.18,
        'katadata.co.id' => 0.15,
        'kompas.com' => 0.10,
        'idx.co.id' => 0.25,
        'ojk.go.id' => 0.25,
        'finance.detik.com' => 0.20,
        'detik.com' => 0.15,
    ];

    public function score(Stock $stock, array $article, ?string $provider = null): array
    {
        $sourceWeights = config('news.source_weights', []);
        $sourceWeight = (float) ($provider && isset($sourceWeights[$provider]) ? $sourceWeights[$provider] : 1.0);
        $normalizedSourceWeight = max(0.0, min(1.0, $sourceWeight / max(1.0, max($sourceWeights ?: [1]))));

        $textTitle = strtolower($article['title'] ?? '');
        $textBody = strtolower(implode(' ', array_filter([
            $article['summary'] ?? '',
            $article['content_snippet'] ?? '',
            $article['full_text'] ?? '',
        ])));
        $text = trim($textTitle.' '.$textBody);

        $keywords = $this->mapper->keywords($stock);
        $contextKeywords = config('news.context_keywords', []);
        $idxContextKeywords = [
            'saham', 'bursa', 'ihsg', 'idx', 'bei', 'emiten',
            'investasi', 'investor', 'portofolio', 'dividen',
            'bank', 'perbankan', 'kredit', 'npf', 'npl', 'car',
            'laba', 'rugi', 'pendapatan', 'revenue', 'profit',
            'rights issue', 'buyback', 'akuisisi', 'merger',
            'ipo', 'obligasi', 'sukuk', 'bi rate', 'inflasi', 'kurs', 'rupiah',
        ];
        $contextKeywords = array_values(array_unique(array_merge($contextKeywords, $idxContextKeywords)));
        $matched = [];

        $relevanceScore = 0.0;
        $entityScore = 0.0;
        $marketScore = 0.0;
        $languageScore = 0.0;
        $flags = [];

        $language = strtolower($article['language'] ?? $article['detected_language'] ?? '');
        if (in_array($language, ['id', 'id-id', 'id_id', 'idn'])) {
            $languageScore = 1.0;
            $language = 'id';
        } elseif (in_array($language, ['en', 'en-us', 'en_us', 'eng'])) {
            $languageScore = 0.9;
            $language = 'en';
        } elseif (! $language) {
            $languageScore = 0.5;
            $language = null;
            $flags[] = 'language_unknown';
        } else {
            $languageScore = 0.1;
            $flags[] = 'language_non_id_en';
        }

        // Ticker/alias/company in title/body
        foreach ($keywords as $kw) {
            $low = strtolower($kw);
            if ($low && str_contains($textTitle, $low)) {
                $relevanceScore += 0.4;
                $entityScore += 0.55;
                $matched[] = $kw;
            } elseif ($low && str_contains($textBody, $low)) {
                $relevanceScore += 0.24;
                $entityScore += 0.3;
                $matched[] = $kw;
            }
        }

        // Context terms (pasar modal)
        $ctxMatches = 0;
        foreach ($contextKeywords as $ctx) {
            $low = strtolower($ctx);
            if ($low && (str_contains($textTitle, $low) || str_contains($textBody, $low))) {
                $ctxMatches++;
                $matched[] = $ctx;
            }
        }
        $marketScore += min(0.35, $ctxMatches * 0.07);
        $relevanceScore += min(0.25, $ctxMatches * 0.08);
        if ($ctxMatches >= 2) {
            $marketScore += 0.3;
        } elseif ($ctxMatches === 1) {
            $marketScore += 0.15;
        }

        // Sector-level entity hints (untuk artikel sektor yang tidak sebut ticker eksplisit)
        $sectorEntities = [
            'Perbankan' => ['ojk', 'bi rate', 'bank indonesia', 'lps', 'otoritas jasa keuangan', 'perbankan', 'ihsg', 'bei', 'bursa efek'],
            'Keuangan' => ['ojk', 'bi rate', 'bank indonesia', 'lps', 'perbankan', 'ihsg', 'bei', 'bursa efek'],
            'Teknologi' => ['ojk', 'kominfo', 'teknologi', 'startup', 'digital'],
            'Energi' => ['esdm', 'pertamina', 'pln', 'energi', 'batubara', 'minyak'],
        ];
        $sectorEntityList = $sectorEntities[$stock->sector ?? ''] ?? [];
        if ($sectorEntityList) {
            $sectorMatches = collect($sectorEntityList)->filter(fn ($e) => $e && Str::contains($text, strtolower($e)))->count();
            if ($sectorMatches >= 2) {
                $entityScore = min(1.0, $entityScore + 0.25);
            } elseif ($sectorMatches === 1) {
                $entityScore = min(1.0, $entityScore + 0.10);
            }
        }

        // Exclusion/ambiguity handling per emiten (mis. GOTO, ASII)
        $exclusions = $this->mapper->exclusionKeywords($stock);
        foreach ($exclusions as $ex) {
            $low = strtolower($ex);
            if ($low && (str_contains($textTitle, $low) || str_contains($textBody, $low))) {
                $marketScore -= 0.15;
                $relevanceScore -= 0.1;
                $flags[] = 'hit_exclusion:'.$ex;
            }
        }

        // Structural quality
        if (! ($article['title'] ?? null)) {
            $relevanceScore -= 0.2;
            $flags[] = 'missing_title';
        }
        if (! ($article['published_at'] ?? null)) {
            $relevanceScore -= 0.1;
        }
        if (! ($article['summary'] ?? null)) {
            $relevanceScore -= 0.05;
        }
        if (! ($article['source_url'] ?? null)) {
            $relevanceScore -= 0.05;
            $flags[] = 'missing_source_url';
        }

        $relevanceScore = max(0.0, min(1.0, $relevanceScore * $sourceWeight));
        $entityScore = max(0.0, min(1.0, $entityScore));
        $marketScore = max(0.0, min(1.0, $marketScore));
        $languageScore = max(0.0, min(1.0, $languageScore));

        // Trust bonus berdasarkan domain sumber
        $sourceUrl = $article['source_url'] ?? $article['url'] ?? '';
        $domain = strtolower(parse_url($sourceUrl, PHP_URL_HOST) ?? '');
        $trustBonus = 0.0;
        foreach ($this->trustedDomains as $trustedDomain => $bonus) {
            if ($domain && str_contains($domain, $trustedDomain)) {
                $trustBonus = $bonus;
                break;
            }
        }

        $finalQuality = (
            ($relevanceScore * 0.33) +
            ($entityScore * 0.27) +
            ($marketScore * 0.22) +
            ($languageScore * 0.08) +
            ($normalizedSourceWeight * 0.10)
        );

        $finalQuality = max(0.0, min(1.0, $finalQuality + $trustBonus));

        $high = (float) config('news.high_threshold', 0.65);
        $medium = (float) config('news.relevance_threshold', 0.35);
        $qualityHigh = (float) config('news.quality_high', 0.7);
        $qualityMedium = (float) config('news.quality_medium', 0.5);

        $band = 'low';
        if ($relevanceScore >= $high) {
            $band = 'high';
        } elseif ($relevanceScore >= $medium) {
            $band = 'medium';
        }

        $qualityBand = 'low';
        if ($finalQuality >= $qualityHigh) {
            $qualityBand = 'high';
        } elseif ($finalQuality >= $qualityMedium) {
            $qualityBand = 'medium';
        }

        return [
            'relevance_score' => round($relevanceScore, 3),
            'relevance_band' => $band,
            'entity_match_score' => round($entityScore, 3),
            'market_context_score' => round($marketScore, 3),
            'language_score' => round($languageScore, 3),
            'final_quality_score' => round($finalQuality, 3),
            'quality_band' => $qualityBand,
            'source_weight' => $sourceWeight,
            'matched_keywords' => array_values(array_unique($matched)),
            'detected_language' => $language,
            'quality_flags' => $flags,
        ];
    }
}
