<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use Illuminate\Database\Eloquent\Builder;
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

        return view('sentiment-validation.index', [
            'title' => 'Label Manual: ML vs Rule-based',
            'subtitle' => 'Validasi Kualitas Sentimen (Gap 2)',
            'description' => 'Artikel di bawah ini adalah kasus di mana model ML dan rule-based BERBEDA PENDAPAT soal sentimen. Baca judul + ringkasan, lalu pilih menurut kamu artikel ini nadanya positif/netral/negatif untuk emitennya.',
            'doneMessage' => 'Semua artikel disagreement sudah kamu label 🎉',
            'nextRoute' => route('sentiment-validation.next'),
            'summaryRoute' => route('sentiment-validation.summary'),
            'sampleMethod' => 'legacy_hard_case',
            'totalDisagreements' => $totalDisagreements,
            'labeledByUser' => $labeledByUser,
        ]);
    }

    public function activeLearning(): View
    {
        $userId = Auth::id();
        $totalDisagreements = $this->activeLearningQuery($userId)->count();
        $labeledByUser = SentimentManualLabel::where('user_id', $userId)->count();

        return view('sentiment-validation.index', [
            'title' => 'Q2: Label Kandidat Positif',
            'subtitle' => 'Active Learning Sentimen Positif',
            'description' => 'Artikel ini belum dilabel manual dan diprioritaskan karena condong positif atau ambigu dekat kelas positif. Skor ML/rule hanya petunjuk sampling, bukan jawaban. Isi berdasarkan dampak berita ke emiten.',
            'doneMessage' => 'Semua kandidat Q2 active-learning sudah kamu label 🎉',
            'nextRoute' => route('sentiment-validation.active-learning.next'),
            'summaryRoute' => route('sentiment-validation.summary'),
            'sampleMethod' => 'legacy_hard_case',
            'totalDisagreements' => $totalDisagreements,
            'labeledByUser' => $labeledByUser,
        ]);
    }

    public function representativeSample(): View
    {
        $userId = Auth::id();
        $totalDisagreements = $this->representativeQuery($userId)->count();
        $labeledByUser = SentimentManualLabel::where('user_id', $userId)
            ->where('sample_method', 'representative_random')
            ->count();

        return view('sentiment-validation.index', [
            'title' => 'R5a: Label Sampel Representatif',
            'subtitle' => 'Random Representatif Populasi Berita',
            'description' => 'Artikel dipilih acak dari populasi berita yang belum kamu label, tanpa filter sentimen/ML/rule. Tujuannya membuat test set representatif, bukan mengejar kasus sulit saja. Target awal 150–200 label.',
            'doneMessage' => 'Semua kandidat representatif yang tersedia sudah kamu label 🎉',
            'nextRoute' => route('sentiment-validation.representative.next'),
            'summaryRoute' => route('sentiment-validation.summary'),
            'sampleMethod' => 'representative_random',
            'totalDisagreements' => $totalDisagreements,
            'labeledByUser' => $labeledByUser,
        ]);
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
                'stock' => $article->stock?->code,
                'published_at' => optional($article->published_at)->toDateString(),
                'ml_label' => $article->ml_sentiment_label,
                'rule_label' => $article->rule_sentiment_label,
                'ml_prob_positive' => $article->ml_prob_positive,
                'ml_prob_neutral' => $article->ml_prob_neutral,
                'ml_prob_negative' => $article->ml_prob_negative,
                'source_url' => $article->source_url,
            ],
            'progress' => [
                'labeled' => SentimentManualLabel::where('user_id', $userId)->count(),
                'total' => NewsArticle::where('ml_rule_agree', false)->count(),
            ],
        ]);
    }

    public function activeLearningNext(): JsonResponse
    {
        $userId = Auth::id();
        $article = $this->activeLearningQuery($userId)
            ->with('stock')
            ->orderByDesc('ml_prob_positive')
            ->orderByDesc('published_at')
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
                'stock' => $article->stock?->code,
                'published_at' => optional($article->published_at)->toDateString(),
                'ml_label' => $article->ml_sentiment_label,
                'rule_label' => $article->rule_sentiment_label,
                'ml_prob_positive' => $article->ml_prob_positive,
                'ml_prob_neutral' => $article->ml_prob_neutral,
                'ml_prob_negative' => $article->ml_prob_negative,
                'source_url' => $article->source_url,
            ],
            'progress' => [
                'labeled' => SentimentManualLabel::where('user_id', $userId)->count(),
                'total' => $this->activeLearningQuery($userId)->count(),
            ],
        ]);
    }

    public function representativeSampleNext(): JsonResponse
    {
        $userId = Auth::id();
        $article = $this->representativeQuery($userId)
            ->with('stock')
            ->inRandomOrder()
            ->first();

        if (! $article) {
            return response()->json(['done' => true]);
        }

        return response()->json([
            'done' => false,
            'article' => $this->articlePayload($article),
            'progress' => [
                'labeled' => SentimentManualLabel::where('user_id', $userId)
                    ->where('sample_method', 'representative_random')
                    ->count(),
                'total' => $this->representativeQuery($userId)->count(),
            ],
        ]);
    }

    public function store(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'news_article_id' => ['required', 'integer', 'exists:news_articles,id'],
            'label' => ['required', 'string', 'in:'.implode(',', SentimentManualLabel::LABELS)],
            'sample_method' => ['nullable', 'string', 'in:'.implode(',', SentimentManualLabel::SAMPLE_METHODS)],
        ]);

        SentimentManualLabel::updateOrCreate(
            ['news_article_id' => $validated['news_article_id'], 'user_id' => Auth::id()],
            [
                'label' => $validated['label'],
                'sample_method' => $validated['sample_method'] ?? 'legacy_hard_case',
            ]
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

    private function activeLearningQuery(int $userId): Builder
    {
        return NewsArticle::query()
            ->whereDoesntHave('manualLabels', fn (Builder $query) => $query->where('user_id', $userId))
            ->whereNotNull('ml_prob_positive')
            ->where(function (Builder $query): void {
                $query->where('ml_sentiment_label', 'positive')
                    ->orWhere('rule_sentiment_label', 'positive')
                    ->orWhere('ml_prob_positive', '>=', 0.35)
                    ->orWhereRaw($this->topProbabilitySql().' - COALESCE(ml_prob_positive, 0) <= ?', [0.15]);
            });
    }

    private function representativeQuery(int $userId): Builder
    {
        return NewsArticle::query()
            ->whereDoesntHave('manualLabels', fn (Builder $query) => $query->where('user_id', $userId))
            ->whereNotNull('title')
            ->where(function (Builder $query): void {
                $query->whereNotNull('summary')
                    ->orWhereNotNull('content_snippet');
            });
    }

    private function articlePayload(NewsArticle $article): array
    {
        return [
            'id' => $article->id,
            'title' => $article->title,
            'summary' => $article->summary ?? $article->content_snippet,
            'source' => $article->source_provider,
            'stock' => $article->stock?->code,
            'published_at' => optional($article->published_at)->toDateString(),
            'ml_label' => $article->ml_sentiment_label,
            'rule_label' => $article->rule_sentiment_label,
            'ml_prob_positive' => $article->ml_prob_positive,
            'ml_prob_neutral' => $article->ml_prob_neutral,
            'ml_prob_negative' => $article->ml_prob_negative,
            'source_url' => $article->source_url,
        ];
    }

    private function topProbabilitySql(): string
    {
        return <<<'SQL'
(CASE
    WHEN COALESCE(ml_prob_positive, 0) >= COALESCE(ml_prob_neutral, 0)
        AND COALESCE(ml_prob_positive, 0) >= COALESCE(ml_prob_negative, 0)
        THEN COALESCE(ml_prob_positive, 0)
    WHEN COALESCE(ml_prob_neutral, 0) >= COALESCE(ml_prob_negative, 0)
        THEN COALESCE(ml_prob_neutral, 0)
    ELSE COALESCE(ml_prob_negative, 0)
END)
SQL;
    }
}
