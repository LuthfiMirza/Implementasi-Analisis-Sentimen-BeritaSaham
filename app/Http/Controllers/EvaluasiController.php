<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Services\Analytics\DecisionSupportService;
use App\Services\Stocks\PriceSeriesService;

class EvaluasiController extends Controller
{
    public function index()
    {
        $stocks = Stock::where('is_active', 1)->get();
        $priceSeriesService = app(PriceSeriesService::class);
        $results = [];

        foreach ($stocks as $stock) {
            $prices = $priceSeriesService->getSeries($stock, '1d', 60);

            $articles = NewsArticle::where('stock_id', $stock->id)
                ->latest()->limit(50)->get();

            $svc = app(DecisionSupportService::class);
            $result = $svc->analyze($stock, $prices, $articles, []);

            $results[] = [
                'code' => $stock->code,
                'name' => $stock->company_name,
                'sector' => $stock->sector,
                'score' => round($result['final_score'] ?? 0, 2),
                'status' => $result['status'] ?? 'N/A',
                'prediction' => $result['prediction'] ?? 'N/A',
                'confidence' => $result['prediction_confidence'] ?? 0,
                'sentiment_avg' => $result['prediction_features']['sentiment_average'] ?? 0,
                'news_count' => $articles->count(),
                'candle_count' => count($prices),
                'pbv' => $stock->pbv,
                'per' => $stock->per,
                'roe' => $stock->roe,
                'fundamentals_updated_at' => $stock->fundamentals_updated_at,
                'macd_trend' => $result['indicators']['macd']['trend'] ?? null,
                'bb_position' => $result['indicators']['bollinger']['position'] ?? null,
                'stoch_signal' => $result['indicators']['stochastic']['signal'] ?? null,
                'obv_trend' => $result['indicators']['obv']['trend'] ?? null,
                'adx_strength' => $result['indicators']['adx']['strength'] ?? null,
                'rsi' => $result['indicators']['rsi'] ?? null,
                'scenario_bull' => $result['scenario_bullish'] ?? null,
                'scenario_flat' => $result['scenario_neutral'] ?? null,
                'scenario_bear' => $result['scenario_bearish'] ?? null,
            ];
        }

        // Summary stats
        $summary = [
            'total_stocks' => count($results),
            'pred_up' => count(array_filter($results, fn ($r) => $r['prediction'] === 'up')),
            'pred_flat' => count(array_filter($results, fn ($r) => $r['prediction'] === 'flat')),
            'pred_down' => count(array_filter($results, fn ($r) => $r['prediction'] === 'down')),
            'avg_score' => count($results) ? round(array_sum(array_column($results, 'score')) / count($results), 2) : 0,
            'avg_confidence' => count($results) ? round(array_sum(array_column($results, 'confidence')) / count($results), 2) : 0,
            'avg_news' => count($results) ? round(array_sum(array_column($results, 'news_count')) / count($results), 1) : 0,
            'high_coverage' => count(array_filter($results, fn ($r) => $r['news_count'] >= 10)),
            'low_coverage' => count(array_filter($results, fn ($r) => $r['news_count'] < 5)),
        ];

        $mlStats = NewsArticle::whereNotNull('ml_sentiment_label')
            ->selectRaw('count(*) as total, sum(case when ml_rule_agree = 1 then 1 else 0 end) as agree, sum(case when ml_rule_agree = 0 then 1 else 0 end) as disagree')
            ->first();
        $summary['ml_total'] = $mlStats->total ?? 0;
        $summary['ml_agree_rate'] = ($mlStats->total ?? 0) > 0
            ? round(($mlStats->agree ?? 0) / $mlStats->total * 100, 1)
            : 0;

        return view('evaluasi.index', compact('results', 'summary'));
    }

    public function show(string $code)
    {
        $stock = Stock::where('code', strtoupper($code))
            ->where('is_active', true)
            ->firstOrFail();

        $prices = app(PriceSeriesService::class)->getSeries($stock, '1d', 60);

        $articles = NewsArticle::where('stock_id', $stock->id)
            ->orderByDesc('final_quality_score')
            ->orderByDesc('published_at')
            ->limit(50)
            ->get();

        $svc = app(DecisionSupportService::class);
        $result = $svc->analyze($stock, $prices, $articles, []);

        $priceChart = $prices->map(fn ($p) => [
            'date' => $p->price_date?->format('d M'),
            'close' => (float) $p->close,
        ])->values();

        $sentimentTrend = $articles
            ->groupBy(fn ($a) => $a->published_at?->format('Y-m-d'))
            ->map(fn ($group) => [
                'date' => $group->first()->published_at?->format('d M'),
                'positive' => $group->where('sentiment_label', 'positive')->count(),
                'negative' => $group->where('sentiment_label', 'negative')->count(),
                'neutral' => $group->where('sentiment_label', 'neutral')->count(),
            ])->values()->take(14);

        return view('evaluasi.show', [
            'stock' => $stock,
            'result' => $result,
            'articles' => $articles,
            'prices' => $prices,
            'priceChart' => $priceChart,
            'sentimentTrend' => $sentimentTrend,
        ]);
    }

    public function sentimen()
    {
        $articles = NewsArticle::whereNotNull('ml_sentiment_label')
            ->whereNotNull('rule_sentiment_label')
            ->get();

        $total = $articles->count();
        if ($total === 0) {
            return view('evaluasi.sentimen', ['empty' => true]);
        }

        $agree = $articles->where('ml_rule_agree', true)->count();
        $disagree = $articles->where('ml_rule_agree', false)->count();
        $agreeRate = $total > 0 ? round($agree / $total * 100, 1) : 0;

        $labels = ['positive', 'neutral', 'negative'];
        $matrix = [];
        foreach ($labels as $rule) {
            foreach ($labels as $ml) {
                $matrix[$rule][$ml] = $articles
                    ->where('rule_sentiment_label', $rule)
                    ->where('ml_sentiment_label', $ml)
                    ->count();
            }
        }

        $mlDist = [
            'positive' => $articles->where('ml_sentiment_label', 'positive')->count(),
            'neutral' => $articles->where('ml_sentiment_label', 'neutral')->count(),
            'negative' => $articles->where('ml_sentiment_label', 'negative')->count(),
        ];

        $ruleDist = [
            'positive' => $articles->where('rule_sentiment_label', 'positive')->count(),
            'neutral' => $articles->where('rule_sentiment_label', 'neutral')->count(),
            'negative' => $articles->where('rule_sentiment_label', 'negative')->count(),
        ];

        $metrics = [];
        foreach ($labels as $label) {
            $tp = $matrix[$label][$label] ?? 0;
            $fp = array_sum(array_column($matrix, $label)) - $tp;
            $fn = array_sum($matrix[$label] ?? []) - $tp;

            $precision = ($tp + $fp) > 0 ? round($tp / ($tp + $fp), 3) : 0;
            $recall = ($tp + $fn) > 0 ? round($tp / ($tp + $fn), 3) : 0;
            $f1 = ($precision + $recall) > 0 ? round(2 * $precision * $recall / ($precision + $recall), 3) : 0;

            $metrics[$label] = compact('precision', 'recall', 'f1', 'tp', 'fp', 'fn');
        }

        $disagreements = $articles->where('ml_rule_agree', false)
            ->sortByDesc('ml_confidence')
            ->take(10)
            ->values();

        $perStock = Stock::where('is_active', true)->get()->map(function ($stock) {
            $arts = NewsArticle::where('stock_id', $stock->id)
                ->whereNotNull('ml_sentiment_label')
                ->whereNotNull('rule_sentiment_label')
                ->get();

            $total = $arts->count();
            $agree = $arts->where('ml_rule_agree', true)->count();

            return [
                'code' => $stock->code,
                'total' => $total,
                'agree' => $agree,
                'agree_rate' => $total > 0 ? round($agree / $total * 100, 1) : 0,
                'ml_pos' => $arts->where('ml_sentiment_label', 'positive')->count(),
                'ml_neu' => $arts->where('ml_sentiment_label', 'neutral')->count(),
                'ml_neg' => $arts->where('ml_sentiment_label', 'negative')->count(),
            ];
        });

        $avgMlConfidence = $articles->avg('ml_confidence') ?? 0;

        return view('evaluasi.sentimen', compact(
            'total',
            'agree',
            'disagree',
            'agreeRate',
            'matrix',
            'mlDist',
            'ruleDist',
            'metrics',
            'disagreements',
            'perStock',
            'labels',
            'avgMlConfidence'
        ));
    }
}
