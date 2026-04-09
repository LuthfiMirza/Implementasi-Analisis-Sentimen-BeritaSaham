<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class NewsArticleController extends Controller
{
    /**
     * Display a listing of the resource.
     */
    public function index()
    {
        $articles = NewsArticle::with(['stock', 'source'])
            ->latest('published_at')
            ->paginate(15);

        return view('admin.news-articles.index', compact('articles'));
    }

    /**
     * Show the form for creating a new resource.
     */
    public function create()
    {
        return view('admin.news-articles.create', [
            'stocks' => Stock::orderBy('code')->get(),
            'sources' => NewsSource::orderBy('name')->get(),
            'article' => new NewsArticle(),
        ]);
    }

    /**
     * Store a newly created resource in storage.
     */
    public function store(Request $request)
    {
        $validated = $this->validateData($request);
        NewsArticle::create($validated);

        return redirect()->route('admin.news-articles.index')->with('status', 'Artikel disimpan.');
    }

    /**
     * Display the specified resource.
     */
    public function show(NewsArticle $newsArticle)
    {
        //
    }

    /**
     * Show the form for editing the specified resource.
     */
    public function edit(NewsArticle $newsArticle)
    {
        return view('admin.news-articles.edit', [
            'article' => $newsArticle,
            'stocks' => Stock::orderBy('code')->get(),
            'sources' => NewsSource::orderBy('name')->get(),
        ]);
    }

    /**
     * Update the specified resource in storage.
     */
    public function update(Request $request, NewsArticle $newsArticle)
    {
        $validated = $this->validateData($request, $newsArticle->id);
        $newsArticle->update($validated);

        return redirect()->route('admin.news-articles.index')->with('status', 'Artikel diperbarui.');
    }

    /**
     * Remove the specified resource from storage.
     */
    public function destroy(NewsArticle $newsArticle)
    {
        $newsArticle->delete();

        return redirect()->route('admin.news-articles.index')->with('status', 'Artikel dihapus.');
    }

    protected function validateData(Request $request, ?int $ignoreId = null): array
    {
        $data = $request->validate([
            'stock_id' => ['nullable', 'exists:stocks,id'],
            'news_source_id' => ['nullable', 'exists:news_sources,id'],
            'title' => ['required', 'string'],
            'slug' => ['nullable', 'string', 'unique:news_articles,slug'.($ignoreId ? ','.$ignoreId : '')],
            'source_url' => ['required', 'url', 'unique:news_articles,source_url'.($ignoreId ? ','.$ignoreId : '')],
            'published_at' => ['nullable', 'date'],
            'summary' => ['nullable', 'string'],
            'content_snippet' => ['nullable', 'string'],
            'full_text' => ['nullable', 'string'],
            'sentiment_label' => ['nullable', 'in:positive,neutral,negative'],
            'sentiment_score' => ['nullable', 'numeric', 'between:-1,1'],
            'language' => ['nullable', 'string', 'max:5'],
        ]);

        $data['slug'] = $data['slug'] ?? Str::slug($data['title']);
        $data['language'] = $data['language'] ?? 'id';

        return $data;
    }
}
