<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use App\Services\News\NewsAggregationService;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class NewsController extends Controller
{
    public function __construct(
        protected NewsAggregationService $aggregationService,
    ) {
    }

    public function index(Request $request)
    {
        $stockCode = $request->query('code');
        $sentiment = $request->query('sentiment');
        $date = $request->query('date');
        $search = $request->query('q');
        $sourceId = $request->query('source');
        $method = $request->query('method');
        $quality = $request->query('quality');
        $relevanceBand = $request->query('relevance');
        $sort = $request->query('sort', 'quality');

        $query = NewsArticle::with(['stock', 'source']);

        if ($stockCode) {
            $stock = Stock::where('code', $stockCode)->first();
            if ($stock) {
                $query->forStockContext($stock);
            }
        }

        if ($sentiment) {
            if ($sentiment === 'unavailable') {
                $query->where('sentiment_method', 'python_unavailable');
            } else {
                $query->where('sentiment_label', $sentiment)
                    ->where(function ($builder) {
                        $builder->whereNull('sentiment_method')
                            ->orWhere('sentiment_method', '!=', 'python_unavailable');
                    });
            }
        }

        if ($method) {
            $query->where('sentiment_method', $method);
        }

        if ($quality) {
            $query->where('quality_band', $quality);
        }

        if ($relevanceBand) {
            $query->where('relevance_band', $relevanceBand);
        }

        if ($date) {
            $query->whereDate('published_at', $date);
        }

        if ($search) {
            $query->where('title', 'like', '%'.$search.'%');
        }

        if ($sourceId) {
            $query->where('news_source_id', $sourceId);
        }

        // Sorting
        $defaultSort = [
            ['final_quality_score', 'desc'],
            ['published_at', 'desc'],
        ];
        if ($sort === 'sentiment') {
            $query->orderByDesc('sentiment_score')->orderByDesc('sentiment_confidence');
        } elseif ($sort === 'recent') {
            $query->latest('published_at');
        } elseif ($sort === 'relevance') {
            $query->orderByDesc('relevance_score')->orderByDesc('published_at');
        } else {
            foreach ($defaultSort as $order) {
                $query->orderBy($order[0], $order[1]);
            }
        }

        $articles = $query->paginate(12)->withQueryString();

        return view('news.index', [
            'articles' => $articles,
            'stocks' => Stock::orderBy('code')->get(),
            'activeCode' => $stockCode,
            'sources' => NewsSource::orderBy('name')->get(),
            'filters' => [
                'sentiment' => $sentiment,
                'date' => $date,
                'q' => $search,
                'source' => $sourceId,
                'method' => $method,
                'quality' => $quality,
                'relevance' => $relevanceBand,
                'sort' => $sort,
            ],
        ]);
    }

    public function refresh(Request $request, string $code): \Illuminate\Http\JsonResponse
    {
        $stock = Stock::where('code', strtoupper($code))
            ->where('is_active', true)
            ->firstOrFail();

        $stats = $this->aggregationService->refreshFromProvider($stock, 15);
        $articles = $this->aggregationService->fetchLatestArticles($stock, 10);

        return response()->json([
            'success' => true,
            'saved' => $stats['saved'] ?? 0,
            'updated' => $stats['updated'] ?? 0,
            'total' => $articles->count(),
            'articles' => $articles->map(fn ($a) => [
                'title' => $a->title,
                'summary' => Str::limit($a->summary ?? $a->content_snippet, 120),
                'sentiment' => $this->displaySentimentLabel($a),
                'score' => $this->displaySentimentScore($a),
                'quality' => $a->quality_band,
                'source' => $a->source?->name ?? $a->source_provider,
                'sentiment_method' => $a->sentiment_method,
                'sentiment_available' => $this->isSentimentAvailable($a),
                'sentiment_status' => $this->isSentimentAvailable($a) ? 'available' : 'unavailable',
                'python_status' => data_get($a->sentiment_meta, 'python_status'),
                'url' => $a->source_url,
                'published' => $a->published_at?->format('d M H:i'),
                'relative' => $a->published_at?->locale('id')->diffForHumans(now()),
            ])->values(),
        ]);
    }

    protected function isSentimentAvailable(NewsArticle $article): bool
    {
        return ($article->sentiment_method ?? null) !== 'python_unavailable';
    }

    protected function displaySentimentLabel(NewsArticle $article): string
    {
        if (! $this->isSentimentAvailable($article)) {
            return 'unavailable';
        }

        return $article->sentiment_label ?? 'neutral';
    }

    protected function displaySentimentScore(NewsArticle $article): ?float
    {
        if (! $this->isSentimentAvailable($article)) {
            return null;
        }

        return $article->sentiment_score !== null ? (float) $article->sentiment_score : null;
    }
}
