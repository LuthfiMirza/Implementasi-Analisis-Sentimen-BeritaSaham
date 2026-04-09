<?php

namespace App\Services\Analytics;

use App\Models\Stock;
use Illuminate\Support\Collection;

class DecisionSupportService
{
    public function __construct(
        protected ?SentimentPriceAnalyticsService $sentimentPriceAnalyticsService = null,
    ) {
        $this->sentimentPriceAnalyticsService ??= new SentimentPriceAnalyticsService();
    }

    public function analyze(Stock $stock, Collection $prices, Collection $articles, ?array $analytics = null): array
    {
        $orderedPrices = $prices->sortBy('price_date')->values();
        $analytics ??= $this->sentimentPriceAnalyticsService->analyze($stock, $orderedPrices, $articles, $orderedPrices->count() ?: 30);

        $ma5 = $this->movingAverage($orderedPrices, 5);
        $ma20 = $this->movingAverage($orderedPrices, 20);
        $maGap = $this->maGap($ma5, $ma20);
        $rsi = $this->rsi($orderedPrices);
        $momentum = $this->momentumSignal($orderedPrices);
        $supportResistance = $this->supportResistance($orderedPrices);
        $breakout = $this->breakoutStatus($orderedPrices, $supportResistance);

        $sentimentScore = $this->normalizeComponent($analytics['weighted_sentiment'] ?? $analytics['average_sentiment'] ?? 0);
        $trendScore = $this->trendScore($analytics['price_trend'] ?? 'datar', $analytics['cumulative_return'] ?? 0, $maGap);
        $momentumScore = $this->momentumScore($momentum, $rsi, $maGap);
        $volumeScore = $this->volumeScore($analytics['news_volume'] ?? 0, $orderedPrices->count());

        $finalScore = round(
            0.35 * $sentimentScore +
            0.30 * $trendScore +
            0.20 * $momentumScore +
            0.15 * $volumeScore,
            2
        );

        [$status, $confidence] = $this->statusAndConfidence($finalScore, $analytics, $orderedPrices);

        $technical = [
            'ma5' => $ma5,
            'ma20' => $ma20,
            'ma_gap' => $maGap,
            'rsi' => $rsi,
            'momentum' => $momentum,
            'support' => $supportResistance['support'] ?? null,
            'resistance' => $supportResistance['resistance'] ?? null,
            'breakout' => $breakout,
        ];

        $supporting = $this->supportingFactors($analytics, $technical);
        $weakening = $this->weakeningFactors($analytics, $technical);
        $risks = $this->riskFactors($analytics, $technical);
        $invalidation = $this->invalidationRules($technical);

        return [
            'stock' => $stock->code,
            'sentiment_average' => $analytics['average_sentiment'] ?? 0,
            'weighted_sentiment' => $analytics['weighted_sentiment'] ?? 0,
            'sentiment_dominance' => $analytics['sentiment_dominance'] ?? 'neutral',
            'news_volume' => $analytics['news_volume'] ?? 0,
            'price_return' => $analytics['cumulative_return'] ?? null,
            'price_trend' => $analytics['price_trend'] ?? 'datar',
            'momentum_signal' => $momentum,
            'volatility' => $analytics['volatility'] ?? null,
            'same_day_correlation' => $analytics['same_day_correlation'] ?? null,
            'lag_correlations' => $analytics['lag_correlations'] ?? [],
            'status' => $status,
            'confidence' => $confidence,
            'final_score' => $finalScore,
            'technical' => $technical,
            'supporting_factors' => $supporting,
            'weakening_factors' => $weakening,
            'risk_factors' => $risks,
            'invalidation_rules' => $invalidation,
            'narrative' => $this->narrativeSummary($status, $analytics, $technical, $confidence),
            'scenarios' => $this->scenarios($analytics, $technical),
            'insights' => $this->insights($analytics, $technical, $supporting, $weakening),
        ];
    }

    protected function movingAverage(Collection $prices, int $window): ?float
    {
        if ($prices->count() < $window) {
            return null;
        }

        return round($prices->take(-$window)->avg('close'), 2);
    }

    protected function maGap(?float $ma5, ?float $ma20): ?float
    {
        if ($ma5 === null || $ma20 === null || $ma20 == 0.0) {
            return null;
        }

        return ($ma5 - $ma20) / $ma20;
    }

    protected function rsi(Collection $prices, int $period = 14): ?float
    {
        if ($prices->count() <= $period) {
            return null;
        }

        $gains = [];
        $losses = [];
        $ordered = $prices->values();

        for ($i = 1; $i <= $period; $i++) {
            $change = ($ordered[$i]->close - $ordered[$i - 1]->close);
            if ($change > 0) {
                $gains[] = $change;
            } else {
                $losses[] = abs($change);
            }
        }

        $avgGain = array_sum($gains) / max(count($gains), 1);
        $avgLoss = array_sum($losses) / max(count($losses), 1);

        if ($avgLoss == 0.0) {
            return 70;
        }

        $rs = $avgGain / $avgLoss;
        $rsi = 100 - (100 / (1 + $rs));

        return round($rsi, 2);
    }

    protected function momentumSignal(Collection $prices): string
    {
        if ($prices->count() < 2) {
            return 'netral';
        }

        $last = $prices->last()->close;
        $prev = $prices->slice(-2, 1)->first()->close;

        if ($last > $prev) {
            return 'bullish';
        }

        if ($last < $prev) {
            return 'bearish';
        }

        return 'netral';
    }

    protected function supportResistance(Collection $prices): array
    {
        if ($prices->isEmpty()) {
            return ['support' => null, 'resistance' => null];
        }

        $window = min(20, $prices->count());
        $slice = $prices->take(-$window);

        return [
            'support' => round((float) $slice->min('close'), 2),
            'resistance' => round((float) $slice->max('close'), 2),
        ];
    }

    protected function breakoutStatus(Collection $prices, array $sr): ?string
    {
        $last = $prices->last();
        if (! $last || ! $sr['support'] || ! $sr['resistance']) {
            return null;
        }

        if ($last->close >= $sr['resistance'] * 1.01) {
            return 'breakout';
        }
        if ($last->close <= $sr['support'] * 0.99) {
            return 'breakdown';
        }

        return null;
    }

    protected function normalizeComponent(float $value, float $min = -1, float $max = 1): float
    {
        $clamped = max($min, min($max, $value));
        return (($clamped - $min) / ($max - $min)) * 100;
    }

    protected function trendScore(string $priceTrend, ?float $cumulativeReturn, ?float $maGap): float
    {
        $score = 50;
        $score += match ($priceTrend) {
            'naik' => 15,
            'turun' => -15,
            default => 0,
        };

        $score += $cumulativeReturn !== null ? max(-10, min(10, $cumulativeReturn / 3)) : 0;
        $score += $maGap !== null ? max(-10, min(10, $maGap * 100)) : 0;

        return max(0, min(100, $score));
    }

    protected function momentumScore(string $momentum, ?float $rsi, ?float $maGap): float
    {
        $score = 50;
        $score += match ($momentum) {
            'bullish' => 10,
            'bearish' => -10,
            default => 0,
        };

        if ($rsi !== null) {
            if ($rsi >= 60) {
                $score += 10;
            } elseif ($rsi <= 40) {
                $score -= 10;
            }
        }

        if ($maGap !== null) {
            $score += max(-8, min(8, $maGap * 100));
        }

        return max(0, min(100, $score));
    }

    protected function volumeScore(int $newsVolume, int $pricePoints): float
    {
        $expected = max(3, (int) ($pricePoints / 6));
        if ($newsVolume === 0) {
            return 25;
        }

        $ratio = $newsVolume / $expected;
        return max(0, min(100, 45 + ($ratio * 20)));
    }

    protected function statusAndConfidence(float $finalScore, array $analytics, Collection $prices): array
    {
        $status = 'Wait and See';
        if ($finalScore >= 65) {
            $status = 'Bullish Support';
        } elseif ($finalScore <= 40) {
            $status = 'Warning';
        }

        $confidence = 'Sedang';
        $volume = $analytics['news_volume'] ?? 0;
        if ($volume < 3 || $prices->count() < 5) {
            $confidence = 'Rendah';
        } elseif ($finalScore >= 75 && $volume >= 5) {
            $confidence = 'Tinggi';
        }

        return [$status, $confidence];
    }

    protected function supportingFactors(array $analytics, array $technical): array
    {
        return array_values(array_filter([
            ($analytics['weighted_sentiment'] ?? 0) > 0.1 ? 'Sentimen rata-rata positif dan mendukung harga.' : null,
            ($technical['ma_gap'] ?? 0) > 0 ? 'MA5 berada di atas MA20, tren pendek mendukung.' : null,
            ($technical['rsi'] ?? 0) >= 55 ? 'RSI berada di zona momentum sehat.' : null,
            ($technical['breakout'] ?? null) === 'breakout' ? 'Harga menembus resistance, indikasi breakout.' : null,
            ($analytics['same_day_correlation'] ?? 0) > 0.2 ? 'Korelasi sentimen-return selaras (same-day).' : null,
        ]));
    }

    protected function weakeningFactors(array $analytics, array $technical): array
    {
        return array_values(array_filter([
            ($analytics['weighted_sentiment'] ?? 0) < -0.1 ? 'Sentimen negatif mendominasi periode ini.' : null,
            ($technical['ma_gap'] ?? 0) < 0 ? 'MA5 di bawah MA20, tren melemah.' : null,
            ($technical['rsi'] ?? 50) <= 45 ? 'RSI rendah, momentum terbatas.' : null,
            ($technical['breakout'] ?? null) === 'breakdown' ? 'Harga menembus support, risiko breakdown.' : null,
            ($analytics['lag_correlations']['h1'] ?? 0) < -0.2 ? 'Lag H+1 negatif: sentimen buruk diikuti return negatif.' : null,
        ]));
    }

    protected function riskFactors(array $analytics, array $technical): array
    {
        return array_values(array_filter([
            isset($analytics['volatility']) && $analytics['volatility'] > 5 ? 'Volatilitas tinggi, pergerakan harga lebih liar.' : null,
            ($analytics['event_study']['negative_events'][0]['sentiment'] ?? null) ? 'Ada lonjakan sentimen negatif, pantau dampak pasca-event.' : null,
            ($technical['breakout'] ?? null) === 'breakdown' ? 'Harga di bawah support meningkatkan risiko invalidasi.' : null,
        ]));
    }

    protected function invalidationRules(array $technical): array
    {
        return array_values(array_filter([
            $technical['support'] ? 'Status bullish batal jika harga turun di bawah support '.$technical['support'].' dengan volume tinggi.' : null,
            $technical['ma20'] ? 'Pantau jika harga menutup di bawah MA20 beberapa hari berturut-turut.' : null,
            $technical['resistance'] ? 'Bullish butuh konfirmasi di atas resistance '.$technical['resistance'].' untuk bertahan.' : null,
        ]));
    }

    protected function narrativeSummary(string $status, array $analytics, array $technical, string $confidence): string
    {
        $sent = round($analytics['weighted_sentiment'] ?? $analytics['average_sentiment'] ?? 0, 2);
        $trend = $analytics['price_trend'] ?? 'datar';
        $rsi = $technical['rsi'] ?? null;
        $maContext = $technical['ma_gap'] !== null
            ? ($technical['ma_gap'] > 0 ? 'harga di atas MA5/MA20' : 'harga di bawah MA20')
            : 'MA terbatas';

        $pieces = [
            'Sentimen '.($sent >= 0 ? 'positif' : 'negatif').' rata-rata '.$sent,
            'tren harga '.$trend,
            $maContext,
            $rsi ? 'RSI '.$rsi : null,
            'keputusan: '.$status.' (confidence '.$confidence.')',
        ];

        return implode('; ', array_filter($pieces));
    }

    protected function scenarios(array $analytics, array $technical): array
    {
        return [
            'bullish' => 'Jika sentimen bertahan positif dan harga menjaga posisi di atas MA20 / support, indikasi kenaikan berlanjut dengan potensi breakout.',
            'neutral' => 'Jika sentimen bercampur dan harga sideways di sekitar MA20, skenario konsolidasi lebih mungkin.',
            'bearish' => 'Jika sentimen kembali negatif dan harga jatuh di bawah support, kecenderungan melemah dan perlu waspada breakdown.',
            'context' => [
                'correlation' => $analytics['same_day_correlation'] ?? null,
                'lag_h1' => $analytics['lag_correlations']['h1'] ?? null,
                'rsi' => $technical['rsi'] ?? null,
            ],
        ];
    }

    protected function insights(array $analytics, array $technical, array $supporting, array $weakening): array
    {
        return array_values(array_filter([
            'Dominasi sentimen: '.($analytics['sentiment_dominance'] ?? 'neutral'),
            $analytics['news_volume'] ? 'Volume berita: '.$analytics['news_volume'] : null,
            $analytics['same_day_correlation'] !== null ? 'Korelasi same-day: '.$analytics['same_day_correlation'] : null,
            $technical['breakout'] ? 'Status harga: '.$technical['breakout'] : null,
            $supporting ? 'Faktor pendukung: '.implode('; ', array_slice($supporting, 0, 2)) : null,
            $weakening ? 'Faktor pelemah: '.implode('; ', array_slice($weakening, 0, 2)) : null,
        ]));
    }
}
