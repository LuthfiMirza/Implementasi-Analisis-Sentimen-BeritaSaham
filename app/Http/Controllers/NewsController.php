<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use Illuminate\Http\Request;

class NewsController extends Controller
{
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
                $query->where('stock_id', $stock->id);
            }
        }

        if ($sentiment) {
            $query->where('sentiment_label', $sentiment);
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
}
