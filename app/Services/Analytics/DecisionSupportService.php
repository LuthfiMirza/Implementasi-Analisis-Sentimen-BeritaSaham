<?php

namespace App\Services\Analytics;

use App\Models\Stock;
use Carbon\Carbon;
use Carbon\CarbonInterface;
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
        $analysisDate = $this->analysisDate($orderedPrices);
        if ($analytics === null || $analytics === []) {
            $analytics = $this->sentimentPriceAnalyticsService->analyze(
                $stock,
                $orderedPrices,
                $articles,
                $orderedPrices->count() ?: 30,
                $analysisDate
            );
        }

        $ma5 = $this->movingAverage($orderedPrices, 5);
        $ma20 = $this->movingAverage($orderedPrices, 20);
        $maGap = $this->maGap($ma5, $ma20);
        $rsi = $this->rsi($orderedPrices);
        $momentum = $this->momentumSignal($orderedPrices);
        $supportResistance = $this->supportResistance($orderedPrices);
        $breakout = $this->breakoutStatus($orderedPrices, $supportResistance);

        $closes = $orderedPrices->pluck('close')->map(fn ($v) => (float) $v)->values()->all();
        $opens = $orderedPrices->pluck('open')->map(fn ($v) => (float) $v)->values()->all();
        $highs = $orderedPrices->pluck('high')->map(fn ($v) => (float) $v)->values()->all();
        $lows = $orderedPrices->pluck('low')->map(fn ($v) => (float) $v)->values()->all();
        $volumes = $orderedPrices->pluck('volume')->map(fn ($v) => (float) $v)->values()->all();

        $macd = count($closes) >= 35 ? $this->calculateMACD($closes) : null;
        $bollinger = count($closes) >= 20 ? $this->calculateBollingerBands($closes) : null;
        $stochastic = count($closes) >= 17 ? $this->calculateStochastic($highs, $lows, $closes) : null;
        $obv = count($closes) >= 2 ? $this->calculateOBV($closes, $volumes) : null;
        $adx = count($closes) >= 28 ? $this->calculateADX($highs, $lows, $closes) : null;
        $atr = count($closes) >= 15 ? $this->calculateATR($highs, $lows, $closes) : null;
        $vwap = count($closes) >= 5 ? $this->calculateVWAP($highs, $lows, $closes, $volumes) : null;
        $candles = count($closes) >= 3 ? $this->detectCandlestickPatterns($opens, $highs, $lows, $closes) : null;
        $fundamental = $this->calculateFundamentalScore($stock);

        $sentimentScore = $this->normalizeComponent($analytics['weighted_sentiment'] ?? $analytics['average_sentiment'] ?? 0);
        $trendScore = $this->trendScore($analytics['price_trend'] ?? 'datar', $analytics['cumulative_return'] ?? 0, $maGap, $macd, $adx, $vwap);
        $momentumScore = $this->momentumScore($momentum, $rsi, $maGap, $stochastic, $candles);
        $volumeScore = $this->volumeScore($analytics['news_volume'] ?? 0, $orderedPrices->count(), $obv, $analytics['price_trend'] ?? 'datar');
        $volatilityScore = $this->volatilityScore($bollinger);
        $fundamentalScore = $fundamental['score'] ?? 0;

        $finalScore = round(
            0.20 * $sentimentScore +
            0.22 * $trendScore +
            0.18 * $momentumScore +
            0.13 * $volumeScore +
            0.12 * $volatilityScore +
            0.15 * $fundamentalScore,
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
            'macd' => $macd,
            'bollinger' => $bollinger,
            'stochastic' => $stochastic,
            'obv' => $obv,
            'adx' => $adx,
            'atr' => $atr,
            'vwap' => $vwap,
            'candles' => $candles,
            'fundamental' => $fundamental,
        ];

        $supporting = $this->supportingFactors($analytics, $technical);
        $weakening = $this->weakeningFactors($analytics, $technical);
        $risks = $this->riskFactors($analytics, $technical);
        $supporting = array_merge($supporting, $fundamental['signals'] ?? []);
        $risks = array_merge($risks, $fundamental['risks'] ?? []);
        $invalidation = $this->invalidationRules($technical);

        // Prediction integration
        $featureBuilder = app(\App\Services\Prediction\FeatureBuilderService::class);
        $predictor = app(\App\Services\Prediction\BaselinePredictionService::class);
        $predictionFeatures = $featureBuilder->build($stock, $orderedPrices, $articles, $analytics, 30, $analysisDate);
        $predictionResult = $predictor->predict($predictionFeatures);
        $lastCloseVal = (float) ($orderedPrices->last()->close ?? 0);
        $tradingSignal = $this->calculateTradingSignal(
            lastClose: $lastCloseVal,
            technical: $technical,
            atr: $atr,
            vwap: $vwap,
            bollinger: $bollinger,
            adx: $adx,
            macd: $macd,
            obv: $obv,
            stochastic: $stochastic,
            prediction: $predictionResult['predicted_direction'] ?? 'flat'
        );

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
            'indicators' => $technical,
            'fundamental' => $fundamental,
            'supporting_factors' => $supporting,
            'weakening_factors' => $weakening,
            'risk_factors' => $risks,
            'invalidation_rules' => $invalidation,
            'narrative' => $this->narrativeSummary($status, $analytics, $technical, $confidence),
            'scenarios' => $this->scenarios($analytics, $technical),
            'insights' => $this->insights($analytics, $technical, $supporting, $weakening),
            'prediction' => $predictionResult['predicted_direction'] ?? null,
            'prediction_confidence' => $predictionResult['confidence'] ?? null,
            'prediction_method' => $predictionResult['method'] ?? null,
            'prediction_scores' => $predictionResult['scores'] ?? null,
            'prediction_basis' => $predictionResult['prediction_basis'] ?? null,
            'scenario_bullish' => $predictionResult['scenario_bullish'] ?? null,
            'scenario_neutral' => $predictionResult['scenario_neutral'] ?? null,
            'scenario_bearish' => $predictionResult['scenario_bearish'] ?? null,
            'prediction_features' => $predictionFeatures,
            'trading_signal' => $tradingSignal,
        ];
    }

    private function calculateTradingSignal(
        float $lastClose,
        array $technical,
        ?array $atr,
        ?array $vwap,
        ?array $bollinger,
        ?array $adx,
        ?array $macd,
        ?array $obv,
        ?array $stochastic,
        string $prediction
    ): array {
        if (! $atr || $lastClose <= 0) {
            return [
                'valid' => false,
                'quality' => 'invalid',
                'prediction' => $prediction,
                'entry' => 0,
                'entry_zone_low' => 0,
                'entry_zone_high' => 0,
                'stop_recommended' => 0,
                'stop_conservative' => 0,
                'stop_aggressive' => 0,
                'target_2r' => 0,
                'target_3r' => 0,
                'risk_per_share' => 0,
                'rr_ratio_2r' => 0,
                'rr_ratio_3r' => 0,
                'atr_value' => 0,
                'atr_percent' => 0,
                'target_note' => '',
                'lot_size' => 0,
                'lot_value' => 0,
                'risk_amount' => 0,
                'confirmations' => [],
                'warnings' => ['Data tidak cukup untuk sinyal trading'],
                'confirm_count' => 0,
                'warn_count' => 1,
                'vwap' => null,
                'ma20' => 0,
                'bb_upper' => null,
                'bb_lower' => null,
                'support' => 0,
                'resistance' => 0,
                'reason' => 'Data tidak cukup untuk sinyal trading',
            ];
        }

        $atrValue = $atr['atr'];
        $atrPct = $atr['atr_percent'];
        $ma5 = $technical['ma5'] ?? $lastClose;
        $ma20 = $technical['ma20'] ?? $lastClose;
        $support = $technical['support'] ?? ($lastClose * 0.97);
        $resistance = $technical['resistance'] ?? ($lastClose * 1.03);
        $bbUpper = $bollinger['upper'] ?? null;
        $bbLower = $bollinger['lower'] ?? null;
        $bbMiddle = $bollinger['middle'] ?? null;
        $vwapVal = $vwap['vwap'] ?? null;

        $confirmations = [];
        $warnings = [];

        if ($ma5 > $ma20) {
            $confirmations[] = 'MA5 > MA20 — uptrend aktif';
        } else {
            $warnings[] = 'MA5 < MA20 — belum uptrend';
        }

        if ($vwapVal && $lastClose > $vwapVal) {
            $confirmations[] = 'Harga di atas VWAP — buyer in control';
        } else {
            $warnings[] = 'Harga di bawah VWAP — waspadai tekanan jual';
        }

        if (($macd['trend'] ?? '') === 'bullish') {
            $confirmations[] = 'MACD bullish — momentum positif';
        } else {
            $warnings[] = 'MACD belum bullish';
        }

        $adxStrength = $adx['strength'] ?? 'weak';
        if ($adxStrength === 'strong') {
            $confirmations[] = 'ADX strong — tren kuat terkonfirmasi';
        } elseif ($adxStrength === 'weak') {
            $warnings[] = 'ADX weak — tren belum kuat, hati-hati false breakout';
        }

        if (($obv['trend'] ?? '') === 'rising') {
            $confirmations[] = 'OBV rising — volume mendukung kenaikan';
        }

        if ($atrPct > 4) {
            $warnings[] = 'Volatilitas sangat tinggi (ATR '.$atrPct.'%) — perlebar stop loss';
        } elseif ($atrPct < 1) {
            $warnings[] = 'Volatilitas sangat rendah — momentum mungkin lemah';
        }

        $entryIdeal = round($lastClose, 0);
        $entryZoneLow = round(max($ma20, $vwapVal ?? $ma20) * 0.999, 0);
        $entryZoneHigh = round($lastClose * 1.005, 0);

        $stopConservative = round($entryIdeal - ($atrValue * 1.5), 0);
        $stopAggressive = round($entryIdeal - ($atrValue * 1.0), 0);
        $stopBBLower = $bbLower ? round($bbLower - ($atrValue * 0.3), 0) : null;

        $stopRecommended = $stopConservative;
        if ($stopBBLower && $stopBBLower > $stopConservative) {
            $stopRecommended = $stopBBLower;
        }

        $risk = $entryIdeal - $stopRecommended;
        $atrTarget2R = round($entryIdeal + ($risk * 2), 0);
        $atrTarget3R = round($entryIdeal + ($risk * 3), 0);

        $target2R = $atrTarget2R;
        $target3R = $atrTarget3R;

        $targetNote = '';
        if ($resistance && $target2R > $resistance * 1.05) {
            $targetNote = 'Target melewati resistance — pertimbangkan partial profit di '.number_format($resistance);
        }

        $rrRatio2 = $risk > 0 ? round(($target2R - $entryIdeal) / $risk, 2) : 0;
        $rrRatio3 = $risk > 0 ? round(($target3R - $entryIdeal) / $risk, 2) : 0;

        $modalDefault = 10_000_000;
        $riskPctPerTrade = 0.02;
        $riskAmount = $modalDefault * $riskPctPerTrade;
        $lotSize = $risk > 0 ? floor($riskAmount / $risk) : 0;
        $lotValue = $lotSize * $entryIdeal;

        $confirmCount = count($confirmations);
        $warnCount = count($warnings);

        $quality = match (true) {
            $confirmCount >= 4 && $warnCount === 0 => 'strong',
            $confirmCount >= 3 && $warnCount <= 1 => 'moderate',
            $confirmCount >= 2 => 'weak',
            default => 'invalid',
        };

        $isValid = $prediction === 'up'
            && in_array($quality, ['strong', 'moderate'])
            && $rrRatio2 >= 1.5;

        return [
            'valid' => $isValid,
            'quality' => $quality,
            'prediction' => $prediction,
            'entry' => $entryIdeal,
            'entry_zone_low' => $entryZoneLow,
            'entry_zone_high' => $entryZoneHigh,
            'stop_recommended' => $stopRecommended,
            'stop_conservative' => $stopConservative,
            'stop_aggressive' => $stopAggressive,
            'target_2r' => $target2R,
            'target_3r' => $target3R,
            'risk_per_share' => round($risk, 0),
            'rr_ratio_2r' => $rrRatio2,
            'rr_ratio_3r' => $rrRatio3,
            'atr_value' => round($atrValue, 0),
            'atr_percent' => $atrPct,
            'target_note' => $targetNote,
            'lot_size' => $lotSize,
            'lot_value' => $lotValue,
            'risk_amount' => $riskAmount,
            'confirmations' => $confirmations,
            'warnings' => $warnings,
            'confirm_count' => $confirmCount,
            'warn_count' => $warnCount,
            'vwap' => $vwapVal,
            'ma20' => $ma20,
            'bb_upper' => $bbUpper,
            'bb_lower' => $bbLower,
            'support' => $support,
            'resistance' => $resistance,
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
        $ordered = $prices->take(-($period + 1))->values();

        for ($i = 1; $i < $ordered->count(); $i++) {
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

    protected function analysisDate(Collection $prices): CarbonInterface
    {
        $lastDate = $prices->last()?->price_date;
        if ($lastDate instanceof CarbonInterface) {
            return $lastDate;
        }

        if ($lastDate) {
            return Carbon::parse($lastDate);
        }

        return now();
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

    protected function trendScore(string $priceTrend, ?float $cumulativeReturn, ?float $maGap, ?array $macd, ?array $adx, ?array $vwap): float
    {
        $score = 50;
        $score += match ($priceTrend) {
            'naik' => 15,
            'turun' => -15,
            default => 0,
        };

        $score += $cumulativeReturn !== null ? max(-10, min(10, $cumulativeReturn / 3)) : 0;
        $score += $maGap !== null ? max(-10, min(10, $maGap * 100)) : 0;

        if ($macd) {
            $score += match ($macd['trend'] ?? 'neutral') {
                'bullish' => 10,
                'bearish' => -10,
                default => 0,
            };
            $hist = $macd['histogram'] ?? 0;
            if ($hist > 0) {
                $score += 5;
            } elseif ($hist < 0) {
                $score -= 5;
            }
        }

        if ($adx) {
            $strength = $adx['strength'] ?? 'weak';
            $dir = $adx['direction'] ?? 'neutral';
            if ($strength === 'strong') {
                $score += $dir === 'bullish' ? 10 : ($dir === 'bearish' ? -10 : 0);
            } elseif ($strength === 'moderate') {
                $score += $dir === 'bullish' ? 5 : ($dir === 'bearish' ? -5 : 0);
            }
        }

        if ($vwap) {
            $pos = $vwap['position'] ?? 'neutral';
            if ($pos === 'above') {
                $score += 5;
            } elseif ($pos === 'below') {
                $score -= 5;
            }
        }

        return max(0, min(100, $score));
    }

    protected function momentumScore(string $momentum, ?float $rsi, ?float $maGap, ?array $stoch, ?array $candles): float
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

        if ($stoch && isset($stoch['k'])) {
            $k = $stoch['k'];
            $stochScore = 50;
            if ($k < 20) {
                $stochScore = 80;
            } elseif ($k > 80) {
                $stochScore = 20;
            }
            $score = (0.6 * $score) + (0.4 * $stochScore);
        }

        if ($candles && isset($candles['signal'])) {
            $signal = $candles['signal'];
            if ($signal === 'bullish') {
                $score += 8;
            } elseif ($signal === 'bearish') {
                $score -= 8;
            }
        }

        if ($maGap !== null) {
            $score += max(-8, min(8, $maGap * 100));
        }

        return max(0, min(100, $score));
    }

    protected function volumeScore(int $newsVolume, int $pricePoints, ?array $obv, string $priceTrend): float
    {
        $score = 50;

        if ($obv) {
            $trend = $obv['obv_trend'] ?? 'neutral';
            $div = $obv['divergence'] ?? null;
            if ($div === 'bullish') {
                $score = 85;
            } elseif ($div === 'bearish') {
                $score = 15;
            } elseif ($trend === 'rising' && $priceTrend === 'naik') {
                $score = 80;
            } elseif ($trend === 'falling' && $priceTrend === 'turun') {
                $score = 20;
            }
        } else {
            $expected = max(3, (int) ($pricePoints / 6));
            if ($newsVolume === 0) {
                return 25;
            }
            $ratio = $newsVolume / $expected;
            $score = max(0, min(100, 45 + ($ratio * 20)));
        }

        return max(0, min(100, $score));
    }

    protected function volatilityScore(?array $bollinger): float
    {
        if (! $bollinger) {
            return 50;
        }
        $position = $bollinger['position'] ?? 'neutral';
        return match ($position) {
            'oversold' => 80,
            'overbought' => 20,
            default => 50,
        };
    }

    protected function calculateADX(array $highs, array $lows, array $closes, int $period = 14): ?array
    {
        $len = count($closes);
        if ($len < $period * 2) {
            return null;
        }

        $trs = $pdm = $mdm = [];
        for ($i = 1; $i < $len; $i++) {
            $tr = max(
                $highs[$i] - $lows[$i],
                abs($highs[$i] - $closes[$i - 1]),
                abs($lows[$i] - $closes[$i - 1])
            );
            $trs[] = $tr;

            $upMove = $highs[$i] - $highs[$i - 1];
            $downMove = $lows[$i - 1] - $lows[$i];

            $pdm[] = ($upMove > $downMove && $upMove > 0) ? $upMove : 0;
            $mdm[] = ($downMove > $upMove && $downMove > 0) ? $downMove : 0;
        }

        $smooth = function (array $values) use ($period) {
            $s = array_sum(array_slice($values, 0, $period));
            $smoothed = [$s];
            for ($i = $period; $i < count($values); $i++) {
                $s = $s - ($s / $period) + $values[$i];
                $smoothed[] = $s;
            }
            return $smoothed;
        };

        $trSmooth = $smooth($trs);
        $pdmSmooth = $smooth($pdm);
        $mdmSmooth = $smooth($mdm);

        $plusDI = [];
        $minusDI = [];
        foreach ($trSmooth as $i => $trVal) {
            if ($trVal == 0) {
                $plusDI[] = 0;
                $minusDI[] = 0;
                continue;
            }
            $plusDI[] = 100 * ($pdmSmooth[$i] ?? 0) / $trVal;
            $minusDI[] = 100 * ($mdmSmooth[$i] ?? 0) / $trVal;
        }

        $dx = [];
        foreach ($plusDI as $i => $pdi) {
            $mdi = $minusDI[$i] ?? 0;
            $den = $pdi + $mdi;
            $dx[] = $den == 0 ? 0 : 100 * abs($pdi - $mdi) / $den;
        }

        if (count($dx) < $period) {
            return null;
        }

        $adxSeries = [];
        $adxInit = array_sum(array_slice($dx, 0, $period)) / $period;
        $adxSeries[] = $adxInit;
        for ($i = $period; $i < count($dx); $i++) {
            $adxInit = (($adxInit * ($period - 1)) + $dx[$i]) / $period;
            $adxSeries[] = $adxInit;
        }

        $adxVal = end($adxSeries);
        $plus = end($plusDI);
        $minus = end($minusDI);

        $strength = 'weak';
        if ($adxVal > 40) {
            $strength = 'strong';
        } elseif ($adxVal >= 25) {
            $strength = 'moderate';
        }

        $direction = 'neutral';
        if ($plus > $minus) {
            $direction = 'bullish';
        } elseif ($minus > $plus) {
            $direction = 'bearish';
        }

        return [
            'adx' => round($adxVal, 2),
            'plus_di' => round($plus, 2),
            'minus_di' => round($minus, 2),
            'strength' => $strength,
            'direction' => $direction,
        ];
    }

    protected function calculateATR(array $highs, array $lows, array $closes, int $period = 14): ?array
    {
        $len = count($closes);
        if ($len < $period + 1) {
            return null;
        }

        $trs = [];
        for ($i = 1; $i < $len; $i++) {
            $trs[] = max(
                $highs[$i] - $lows[$i],
                abs($highs[$i] - $closes[$i - 1]),
                abs($lows[$i] - $closes[$i - 1])
            );
        }

        $atr = array_sum(array_slice($trs, 0, $period)) / $period;
        for ($i = $period; $i < count($trs); $i++) {
            $atr = (($atr * ($period - 1)) + $trs[$i]) / $period;
        }

        $lastClose = end($closes);
        $atrPct = $lastClose > 0 ? ($atr / $lastClose) * 100 : 0;
        $volatility = 'normal';
        if ($atrPct > 3) {
            $volatility = 'high';
        } elseif ($atrPct < 1) {
            $volatility = 'low';
        }

        return [
            'atr' => round($atr, 4),
            'atr_percent' => round($atrPct, 2),
            'volatility' => $volatility,
        ];
    }

    protected function calculateVWAP(array $highs, array $lows, array $closes, array $volumes, int $period = 20): ?array
    {
        $len = count($closes);
        if ($len < 3 || count($volumes) !== $len) {
            return null;
        }
        $slice = array_slice($closes, -$period);
        $sliceHighs = array_slice($highs, -$period);
        $sliceLows = array_slice($lows, -$period);
        $sliceVolumes = array_slice($volumes, -$period);

        $tpVolSum = 0;
        $volSum = 0;
        foreach ($slice as $i => $close) {
            $tp = ($sliceHighs[$i] + $sliceLows[$i] + $close) / 3;
            $vol = $sliceVolumes[$i] ?? 0;
            $tpVolSum += $tp * $vol;
            $volSum += $vol;
        }
        if ($volSum == 0) {
            return null;
        }
        $vwap = $tpVolSum / $volSum;
        $lastClose = end($closes);
        $distance = $vwap != 0 ? abs(($lastClose - $vwap) / $vwap) * 100 : null;
        $position = $lastClose > $vwap ? 'above' : ($lastClose < $vwap ? 'below' : 'neutral');

        return [
            'vwap' => round($vwap, 4),
            'position' => $position,
            'distance' => $distance !== null ? round($distance, 2) : null,
        ];
    }

    protected function detectCandlestickPatterns(array $opens, array $highs, array $lows, array $closes): ?array
    {
        $n = count($closes);
        if ($n < 3) {
            return null;
        }

        $patterns = [];

        $c0 = $closes[$n - 1]; $o0 = $opens[$n - 1];
        $h0 = $highs[$n - 1];  $l0 = $lows[$n - 1];
        $c1 = $closes[$n - 2]; $o1 = $opens[$n - 2];
        $h1 = $highs[$n - 2];  $l1 = $lows[$n - 2];
        $c2 = $closes[$n - 3]; $o2 = $opens[$n - 3];

        $body0 = abs($c0 - $o0);
        $body1 = abs($c1 - $o1);
        $range0 = $h0 - $l0;
        $range1 = $h1 - $l1;

        if ($range0 > 0 && ($body0 / $range0) < 0.1) {
            $patterns[] = ['name' => 'Doji', 'signal' => 'neutral', 'description' => 'Indecision — potential reversal'];
        }

        $lowerShadow0 = min($o0, $c0) - $l0;
        $upperShadow0 = $h0 - max($o0, $c0);
        if ($body0 > 0 && $lowerShadow0 >= 2 * $body0 && $upperShadow0 <= $body0 * 0.5) {
            $patterns[] = ['name' => 'Hammer', 'signal' => 'bullish', 'description' => 'Potential bullish reversal'];
        }
        if ($body0 > 0 && $upperShadow0 >= 2 * $body0 && $lowerShadow0 <= $body0 * 0.5) {
            $patterns[] = ['name' => 'Shooting Star', 'signal' => 'bearish', 'description' => 'Potential bearish reversal'];
        }

        if ($c1 < $o1 && $c0 > $o0 && $o0 < $c1 && $c0 > $o1) {
            $patterns[] = ['name' => 'Bullish Engulfing', 'signal' => 'bullish', 'description' => 'Strong bullish reversal signal'];
        }
        if ($c1 > $o1 && $c0 < $o0 && $o0 > $c1 && $c0 < $o1) {
            $patterns[] = ['name' => 'Bearish Engulfing', 'signal' => 'bearish', 'description' => 'Strong bearish reversal signal'];
        }

        $body2 = abs($c2 - $o2);
        if ($c2 < $o2 && ($body1 / ($h1 - $l1 + 0.01)) < 0.3 && $c0 > $o0 && $c0 > ($o2 + $c2) / 2) {
            $patterns[] = ['name' => 'Morning Star', 'signal' => 'bullish', 'description' => 'Strong bullish reversal — 3 candle pattern'];
        }
        if ($c2 > $o2 && ($body1 / ($h1 - $l1 + 0.01)) < 0.3 && $c0 < $o0 && $c0 < ($o2 + $c2) / 2) {
            $patterns[] = ['name' => 'Evening Star', 'signal' => 'bearish', 'description' => 'Strong bearish reversal — 3 candle pattern'];
        }

        $bullish = count(array_filter($patterns, fn ($p) => $p['signal'] === 'bullish'));
        $bearish = count(array_filter($patterns, fn ($p) => $p['signal'] === 'bearish'));
        $signal = 'neutral';
        if ($bullish > $bearish) {
            $signal = 'bullish';
        } elseif ($bearish > $bullish) {
            $signal = 'bearish';
        }

        return [
            'patterns' => $patterns,
            'signal' => $signal,
            'count' => count($patterns),
        ];
    }

    protected function calculateFundamentalScore(Stock $stock): array
    {
        $score = 50;
        $signals = [];
        $risks = [];

        if ($stock->pbv !== null) {
            if ($stock->pbv < 1.0) {
                $score += 15;
                $signals[] = "PBV {$stock->pbv}x — saham undervalued, di bawah book value";
            } elseif ($stock->pbv < 2.0) {
                $score += 8;
                $signals[] = "PBV {$stock->pbv}x — valuasi wajar";
            } elseif ($stock->pbv < 4.0) {
                $score += 2;
            } else {
                $score -= 8;
                $risks[] = "PBV {$stock->pbv}x — valuasi premium, risiko koreksi jika earning miss";
            }
        }

        if ($stock->per !== null && $stock->per > 0) {
            if ($stock->per < 8) {
                $score += 12;
                $signals[] = "PER {$stock->per}x — sangat murah, potensi value trap atau undervalued";
            } elseif ($stock->per < 15) {
                $score += 6;
                $signals[] = "PER {$stock->per}x — valuasi menarik";
            } elseif ($stock->per < 25) {
                $score += 0;
            } else {
                $score -= 6;
                $risks[] = "PER {$stock->per}x — premium tinggi, priced for perfection";
            }
        } elseif ($stock->per === null || $stock->per <= 0) {
            $score -= 10;
            $risks[] = "PER negatif/N/A — perusahaan masih merugi";
        }

        if ($stock->roe !== null) {
            if ($stock->roe >= 20) {
                $score += 12;
                $signals[] = "ROE {$stock->roe}% — profitabilitas sangat baik";
            } elseif ($stock->roe >= 15) {
                $score += 7;
                $signals[] = "ROE {$stock->roe}% — profitabilitas baik";
            } elseif ($stock->roe >= 10) {
                $score += 2;
            } elseif ($stock->roe >= 0) {
                $score -= 3;
            } else {
                $score -= 12;
                $risks[] = "ROE {$stock->roe}% — perusahaan sedang merugi";
            }
        }

        if ($stock->der !== null) {
            $isBank = in_array($stock->sector, ['Perbankan', 'Keuangan', 'Bank']);
            if ($isBank) {
                if ($stock->der >= 4 && $stock->der <= 9) {
                    $score += 3;
                } elseif ($stock->der > 9) {
                    $score -= 5;
                    $risks[] = "DER {$stock->der}x — leverage bank sangat tinggi";
                }
            } else {
                if ($stock->der < 0.5) {
                    $score += 10;
                    $signals[] = "DER {$stock->der}x — leverage sangat rendah, neraca kuat";
                } elseif ($stock->der < 1.5) {
                    $score += 5;
                    $signals[] = "DER {$stock->der}x — leverage moderat, sehat";
                } elseif ($stock->der < 3.0) {
                    $score -= 3;
                    $risks[] = "DER {$stock->der}x — leverage tinggi, pantau cashflow";
                } else {
                    $score -= 10;
                    $risks[] = "DER {$stock->der}x — leverage sangat tinggi, risiko finansial";
                }
            }
        }

        if ($stock->dividend_yield !== null && $stock->dividend_yield > 0) {
            if ($stock->dividend_yield >= 5) {
                $score += 5;
                $signals[] = "Dividend yield {$stock->dividend_yield}% — income stock menarik";
            } elseif ($stock->dividend_yield >= 2) {
                $score += 2;
            }
        }

        $score = max(0, min(100, $score));
        $rating = 'neutral';
        if ($score >= 70) {
            $rating = 'attractive';
        } elseif ($score >= 55) {
            $rating = 'fair';
        } elseif ($score <= 35) {
            $rating = 'expensive';
        }

        return [
            'score' => $score,
            'rating' => $rating,
            'pbv' => $stock->pbv,
            'per' => $stock->per,
            'roe' => $stock->roe,
            'der' => $stock->der,
            'eps' => $stock->eps,
            'dividend_yield' => $stock->dividend_yield,
            'updated_at' => $stock->fundamentals_updated_at,
            'signals' => $signals,
            'risks' => $risks,
        ];
    }

    protected function calculateMACD(array $closes): ?array
    {
        if (count($closes) < 35) {
            return null;
        }

        $ema12 = $this->ema(array_slice($closes, -35), 12);
        $ema26 = $this->ema(array_slice($closes, -35), 26);
        if ($ema12 === null || $ema26 === null) {
            return null;
        }
        $macdLine = $ema12 - $ema26;

        // Build MACD series for last 9 periods to get signal
        $macdSeries = [];
        $slice = array_slice($closes, -35);
        foreach ($slice as $i => $price) {
            $segment = array_slice($slice, 0, $i + 1);
            $e12 = $this->ema($segment, 12);
            $e26 = $this->ema($segment, 26);
            if ($e12 !== null && $e26 !== null) {
                $macdSeries[] = $e12 - $e26;
            }
        }

        $signal = $this->ema($macdSeries, 9);
        if ($signal === null) {
            return null;
        }
        $histogram = $macdLine - $signal;

        $trend = 'neutral';
        if ($macdLine > $signal && $histogram > 0) {
            $trend = 'bullish';
        } elseif ($macdLine < $signal && $histogram < 0) {
            $trend = 'bearish';
        }

        return [
            'macd' => round($macdLine, 4),
            'signal' => round($signal, 4),
            'histogram' => round($histogram, 4),
            'trend' => $trend,
        ];
    }

    protected function calculateBollingerBands(array $closes, int $period = 20, float $stdDev = 2.0): ?array
    {
        if (count($closes) < $period) {
            return null;
        }

        $slice = array_slice($closes, -$period);
        $middle = array_sum($slice) / $period;

        $variance = 0.0;
        foreach ($slice as $price) {
            $variance += pow($price - $middle, 2);
        }
        $variance /= $period;
        $std = sqrt($variance);

        $upper = $middle + ($stdDev * $std);
        $lower = $middle - ($stdDev * $std);
        $lastClose = end($closes);

        $position = 'neutral';
        if ($lastClose > $upper) {
            $position = 'overbought';
        } elseif ($lastClose < $lower) {
            $position = 'oversold';
        }

        $bandwidth = $middle != 0.0 ? (($upper - $lower) / $middle) * 100 : null;
        $percentB = ($upper - $lower) != 0.0 ? ($lastClose - $lower) / ($upper - $lower) : null;

        return [
            'upper' => round($upper, 4),
            'middle' => round($middle, 4),
            'lower' => round($lower, 4),
            'bandwidth' => $bandwidth !== null ? round($bandwidth, 4) : null,
            'percent_b' => $percentB !== null ? round($percentB, 4) : null,
            'position' => $position,
        ];
    }

    protected function calculateStochastic(array $highs, array $lows, array $closes, int $kPeriod = 14, int $dPeriod = 3): ?array
    {
        if (count($highs) < ($kPeriod + $dPeriod)) {
            return null;
        }

        $recentHighs = array_slice($highs, -$kPeriod);
        $recentLows = array_slice($lows, -$kPeriod);
        $recentCloses = array_slice($closes, -($kPeriod + $dPeriod));

        $highestHigh = max($recentHighs);
        $lowestLow = min($recentLows);
        $lastClose = end($closes);

        $denominator = $highestHigh - $lowestLow;
        if ($denominator == 0.0) {
            return null;
        }

        $k = (($lastClose - $lowestLow) / $denominator) * 100;

        // build %K series for last dPeriod to compute %D
        $kSeries = [];
        for ($i = $dPeriod - 1; $i >= 0; $i--) {
            $subsetCloses = array_slice($recentCloses, -$kPeriod - $i, $kPeriod);
            $hh = max(array_slice($highs, -$kPeriod - $i, $kPeriod));
            $ll = min(array_slice($lows, -$kPeriod - $i, $kPeriod));
            $den = $hh - $ll;
            if ($den == 0.0) {
                continue;
            }
            $kSeries[] = ((end($subsetCloses) - $ll) / $den) * 100;
        }
        $d = count($kSeries) ? array_sum($kSeries) / count($kSeries) : null;

        $signal = 'neutral';
        if ($k > 80) {
            $signal = 'overbought';
        } elseif ($k < 20) {
            $signal = 'oversold';
        }

        $cross = null;
        if ($d !== null) {
            $prevK = count($kSeries) > 1 ? $kSeries[count($kSeries) - 2] : null;
            $prevD = count($kSeries) > 1 ? array_sum(array_slice($kSeries, 0, -1)) / (count($kSeries) - 1) : null;
            if ($prevK !== null && $prevD !== null) {
                if ($prevK < $prevD && $k > $d && $k < 20) {
                    $cross = 'bullish';
                } elseif ($prevK > $prevD && $k < $d && $k > 80) {
                    $cross = 'bearish';
                }
            }
        }

        return [
            'k' => round($k, 2),
            'd' => $d !== null ? round($d, 2) : null,
            'signal' => $signal,
            'cross' => $cross,
        ];
    }

    protected function calculateOBV(array $closes, array $volumes): ?array
    {
        if (count($closes) < 2 || count($closes) !== count($volumes)) {
            return null;
        }

        $obvSeries = [];
        $obv = $volumes[0] ?? 0;
        $obvSeries[] = $obv;
        for ($i = 1; $i < count($closes); $i++) {
            if ($closes[$i] > $closes[$i - 1]) {
                $obv += $volumes[$i];
            } elseif ($closes[$i] < $closes[$i - 1]) {
                $obv -= $volumes[$i];
            }
            $obvSeries[] = $obv;
        }

        $obvTrend = 'neutral';
        if (count($obvSeries) > 5) {
            $prev = $obvSeries[count($obvSeries) - 6];
            if ($obv > $prev) {
                $obvTrend = 'rising';
            } elseif ($obv < $prev) {
                $obvTrend = 'falling';
            }
        }

        $divergence = null;
        if (count($closes) > 5) {
            $priceChange = $closes[count($closes) - 1] - $closes[count($closes) - 6];
            $obvChange = $obv - $obvSeries[count($obvSeries) - 6];
            if ($priceChange < 0 && $obvChange > 0) {
                $divergence = 'bullish';
            } elseif ($priceChange > 0 && $obvChange < 0) {
                $divergence = 'bearish';
            }
        }

        return [
            'obv' => $obv,
            'obv_trend' => $obvTrend,
            'divergence' => $divergence,
        ];
    }

    protected function ema(array $values, int $period): ?float
    {
        if (count($values) < $period) {
            return null;
        }
        $k = 2 / ($period + 1);
        $ema = $values[0];
        foreach ($values as $price) {
            $ema = ($price * $k) + ($ema * (1 - $k));
        }
        return $ema;
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
            ($technical['macd']['trend'] ?? null) === 'bullish' ? 'MACD bullish — momentum positif terkonfirmasi.' : null,
            ($technical['bollinger']['position'] ?? null) === 'oversold' ? 'Harga di zona oversold Bollinger — potensi rebound.' : null,
            (($technical['stochastic']['k'] ?? null) !== null && ($technical['stochastic']['k'] < 20) && ($technical['stochastic']['cross'] ?? null) === 'bullish') ? 'Stochastic: sinyal beli dari zona oversold.' : null,
            ($technical['obv']['divergence'] ?? null) === 'bullish' ? 'OBV divergensi bullish — akumulasi terdeteksi.' : null,
            ($technical['obv']['obv_trend'] ?? null) === 'rising' ? 'Volume terbobot (OBV) mengkonfirmasi kenaikan harga.' : null,
            ($technical['adx']['strength'] ?? null) === 'strong' && ($technical['adx']['direction'] ?? null) === 'bullish' ? 'ADX kuat dengan arah bullish — tren solid.' : null,
            ($technical['candles']['signal'] ?? null) === 'bullish' ? 'Pola candlestick bullish terdeteksi: '.implode(', ', array_map(fn($p) => $p['name'], $technical['candles']['patterns'] ?? [])) : null,
            ($technical['atr']['volatility'] ?? null) === 'low' ? 'ATR rendah — volatilitas terkontrol.' : null,
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
            ($technical['macd']['trend'] ?? null) === 'bearish' ? 'MACD bearish — momentum negatif, waspadai penurunan.' : null,
            ($technical['bollinger']['position'] ?? null) === 'overbought' ? 'Harga di zona overbought Bollinger — risiko koreksi.' : null,
            (($technical['stochastic']['k'] ?? null) !== null && ($technical['stochastic']['k'] > 80) && ($technical['stochastic']['cross'] ?? null) === 'bearish') ? 'Stochastic: sinyal jual dari zona overbought.' : null,
            ($technical['obv']['divergence'] ?? null) === 'bearish' ? 'OBV divergensi bearish — distribusi terdeteksi.' : null,
            ($technical['adx']['strength'] ?? null) === 'strong' && ($technical['adx']['direction'] ?? null) === 'bearish' ? 'ADX kuat dengan arah bearish — tren turun solid.' : null,
            ($technical['candles']['signal'] ?? null) === 'bearish' ? 'Pola candlestick bearish terdeteksi: '.implode(', ', array_map(fn($p) => $p['name'], $technical['candles']['patterns'] ?? [])) : null,
        ]));
    }

    protected function riskFactors(array $analytics, array $technical): array
    {
        return array_values(array_filter([
            isset($analytics['volatility']) && $analytics['volatility'] > 5 ? 'Volatilitas tinggi, pergerakan harga lebih liar.' : null,
            ($analytics['event_study']['negative_events'][0]['sentiment'] ?? null) ? 'Ada lonjakan sentimen negatif, pantau dampak pasca-event.' : null,
            ($technical['breakout'] ?? null) === 'breakdown' ? 'Harga di bawah support meningkatkan risiko invalidasi.' : null,
            ($technical['atr']['volatility'] ?? null) === 'high' ? 'ATR tinggi ('.($technical['atr']['atr_percent'] ?? '-').'%) — risiko stop-loss lebih besar.' : null,
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
            ($analytics['news_volume'] ?? 0) ? 'Volume berita: '.($analytics['news_volume'] ?? 0) : null,
            ($analytics['same_day_correlation'] ?? null) !== null ? 'Korelasi same-day: '.($analytics['same_day_correlation'] ?? null) : null,
            $technical['breakout'] ? 'Status harga: '.$technical['breakout'] : null,
            $supporting ? 'Faktor pendukung: '.implode('; ', array_slice($supporting, 0, 2)) : null,
            $weakening ? 'Faktor pelemah: '.implode('; ', array_slice($weakening, 0, 2)) : null,
        ]));
    }
}
