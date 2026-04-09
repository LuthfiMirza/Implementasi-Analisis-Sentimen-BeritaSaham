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

        $query = NewsArticle::with(['stock', 'source'])->latest('published_at');

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

        if ($date) {
            $query->whereDate('published_at', $date);
        }

        if ($search) {
            $query->where('title', 'like', '%'.$search.'%');
        }

        if ($sourceId) {
            $query->where('news_source_id', $sourceId);
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
            ],
        ]);
    }
}
