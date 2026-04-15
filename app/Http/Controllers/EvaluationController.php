<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\Stock;
use Illuminate\Http\Request;

class EvaluationController extends Controller
{
    public function index(Request $request)
    {
        $stockCode = $request->query('code', 'BBCA');
        $stock = Stock::where('code', $stockCode)->firstOrFail();
        $stocks = Stock::where('is_active', true)->orderBy('code')->get();

        $articles = NewsArticle::where('stock_id', $stock->id)
            ->orderByDesc('published_at')
            ->get();

        $sentimentDist = [
            'positive' => $articles->where('sentiment_label', 'positive')->count(),
            'neutral' => $articles->where('sentiment_label', 'neutral')->count(),
            'negative' => $articles->where('sentiment_label', 'negative')->count(),
        ];

        $qualityDist = [
            'high' => $articles->where('relevance_band', 'high')->count(),
            'medium' => $articles->where('relevance_band', 'medium')->count(),
            'low' => $articles->where('relevance_band', 'low')->count(),
        ];

        $providerDist = $articles->groupBy('source_provider')->map->count();
        $sampleArticles = $articles->take(10);

        // Simple keyword-based ground truth for confusion matrix
        $tp = $fp = $tn = $fn = 0;
        foreach ($articles as $a) {
            $text = strtolower($a->title ?? '');
            $positiveWords = ['naik', 'melesat', 'dividen', 'lompat', 'terbang', 'laba', 'menguat', 'rebound', 'surplus'];
            $negativeWords = ['turun', 'anjlok', 'jatuh', 'rugi', 'melemah', 'merah', 'koreksi', 'ambruk'];
            $hasPos = collect($positiveWords)->contains(fn ($w) => str_contains($text, $w));
            $hasNeg = collect($negativeWords)->contains(fn ($w) => str_contains($text, $w));
            $expected = $hasPos && ! $hasNeg ? 'positive' : ($hasNeg && ! $hasPos ? 'negative' : 'neutral');
            $system = $a->sentiment_label ?? 'neutral';
            if ($system === 'positive' && $expected === 'positive') {
                $tp++;
            } elseif ($system === 'positive' && $expected !== 'positive') {
                $fp++;
            } elseif ($system !== 'positive' && $expected === 'positive') {
                $fn++;
            } else {
                $tn++;
            }
        }
        $total = max(1, count($articles));
        $confusionMatrix = [
            'tp' => $tp,
            'fp' => $fp,
            'tn' => $tn,
            'fn' => $fn,
            'accuracy' => round(($tp + $tn) / $total * 100, 1),
            'precision' => $tp + $fp > 0 ? round($tp / ($tp + $fp) * 100, 1) : 0,
            'recall' => $tp + $fn > 0 ? round($tp / ($tp + $fn) * 100, 1) : 0,
            'f1' => 0,
        ];
        $p = $confusionMatrix['precision'];
        $r = $confusionMatrix['recall'];
        $confusionMatrix['f1'] = $p + $r > 0 ? round(2 * $p * $r / ($p + $r), 1) : 0;

        $mlTotal = NewsArticle::where('stock_id', $stock->id)
            ->whereNotNull('ml_sentiment_label')
            ->count();

        $mlDist = [
            'positive' => NewsArticle::where('stock_id', $stock->id)
                ->where('ml_sentiment_label', 'positive')->count(),
            'neutral' => NewsArticle::where('stock_id', $stock->id)
                ->where('ml_sentiment_label', 'neutral')->count(),
            'negative' => NewsArticle::where('stock_id', $stock->id)
                ->where('ml_sentiment_label', 'negative')->count(),
        ];

        $agreementCount = NewsArticle::where('stock_id', $stock->id)
            ->where('ml_rule_agree', true)
            ->count();

        $agreementRate = $mlTotal > 0 ? round($agreementCount / $mlTotal * 100, 1) : 0;

        $differArticles = NewsArticle::where('stock_id', $stock->id)
            ->where('ml_rule_agree', false)
            ->whereNotNull('ml_sentiment_label')
            ->orderByDesc('published_at')
            ->limit(5)
            ->get(['title', 'ml_sentiment_label', 'ml_confidence', 'rule_sentiment_label', 'sentiment_label']);

        $allStocksSummary = Stock::where('is_active', true)->get()->map(function ($s) {
            $arts = NewsArticle::where('stock_id', $s->id)->get();
            return [
                'code' => $s->code,
                'name' => $s->company_name,
                'total' => $arts->count(),
                'positive' => $arts->where('sentiment_label', 'positive')->count(),
                'neutral' => $arts->where('sentiment_label', 'neutral')->count(),
                'negative' => $arts->where('sentiment_label', 'negative')->count(),
            ];
        });

        return view('evaluation.index', compact(
            'stock',
            'stocks',
            'articles',
            'sentimentDist',
            'qualityDist',
            'providerDist',
            'sampleArticles',
            'confusionMatrix',
            'mlTotal',
            'mlDist',
            'agreementCount',
            'agreementRate',
            'differArticles',
            'allStocksSummary'
        ));
    }
}
