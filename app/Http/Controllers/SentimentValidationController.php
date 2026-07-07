<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\View\View;

/**
 * Manual sampling tool for Gap 2 of the project's data-quality remediation plan:
 * sample articles where ML vs rule-based sentiment disagree, collect a human
 * label, then measure agreement rate of each method against human judgement.
 */
class SentimentValidationController extends Controller
{
    public function index(): View
    {
        $userId = Auth::id();
        $totalDisagreements = NewsArticle::where('ml_rule_agree', false)->count();
        $labeledByUser = SentimentManualLabel::where('user_id', $userId)->count();

        return view('sentiment-validation.index', compact('totalDisagreements', 'labeledByUser'));
    }

    public function next(): JsonResponse
    {
        $userId = Auth::id();
        $article = NewsArticle::where('ml_rule_agree', false)
            ->whereDoesntHave('manualLabels', fn ($query) => $query->where('user_id', $userId))
            ->inRandomOrder()
            ->first();

        if (! $article) {
            return response()->json(['done' => true]);
        }

        return response()->json([
            'done' => false,
            'article' => [
                'id' => $article->id,
                'title' => $article->title,
                'summary' => $article->summary ?? $article->content_snippet,
                'source' => $article->source_provider,
            ],
            'progress' => [
                'labeled' => SentimentManualLabel::where('user_id', $userId)->count(),
                'total' => NewsArticle::where('ml_rule_agree', false)->count(),
            ],
        ]);
    }

    public function store(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'news_article_id' => ['required', 'integer', 'exists:news_articles,id'],
            'label' => ['required', 'string', 'in:'.implode(',', SentimentManualLabel::LABELS)],
        ]);

        SentimentManualLabel::updateOrCreate(
            ['news_article_id' => $validated['news_article_id'], 'user_id' => Auth::id()],
            ['label' => $validated['label']]
        );

        return response()->json(['success' => true]);
    }

    public function summary(): View
    {
        $labels = SentimentManualLabel::with('article')->get();

        $mlAgree = 0;
        $ruleAgree = 0;
        $total = $labels->count();
        $confusionMl = [];
        $confusionRule = [];

        foreach ($labels as $manual) {
            $article = $manual->article;
            if (! $article) {
                continue;
            }

            if ($article->ml_sentiment_label === $manual->label) {
                $mlAgree++;
            }
            if ($article->rule_sentiment_label === $manual->label) {
                $ruleAgree++;
            }

            $confusionMl[$article->ml_sentiment_label][$manual->label] = ($confusionMl[$article->ml_sentiment_label][$manual->label] ?? 0) + 1;
            $confusionRule[$article->rule_sentiment_label][$manual->label] = ($confusionRule[$article->rule_sentiment_label][$manual->label] ?? 0) + 1;
        }

        return view('sentiment-validation.summary', [
            'total' => $total,
            'mlAgreeRate' => $total > 0 ? round($mlAgree / $total * 100, 1) : null,
            'ruleAgreeRate' => $total > 0 ? round($ruleAgree / $total * 100, 1) : null,
            'confusionMl' => $confusionMl,
            'confusionRule' => $confusionRule,
        ]);
    }
}
