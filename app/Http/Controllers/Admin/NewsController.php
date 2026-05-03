<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\NewsArticle;
use Illuminate\Http\RedirectResponse;
use Illuminate\View\View;

class NewsController extends Controller
{
    /**
     * Display paginated news articles through the `/admin/news` contract route.
     */
    public function index(): View
    {
        $articles = NewsArticle::query()
            ->with(['stock', 'source'])
            ->latest('published_at')
            ->paginate(20);

        return view('admin.news.index', compact('articles'));
    }

    /**
     * Display one news article for administrator inspection.
     */
    public function show(NewsArticle $news): View
    {
        $article = $news->load(['stock', 'source']);

        return view('admin.news.show', compact('article'));
    }

    /**
     * Delete an article from the admin news alias route.
     */
    public function destroy(NewsArticle $news): RedirectResponse
    {
        $news->delete();

        return redirect()->route('admin.news.index')->with('status', 'Berita berhasil dihapus.');
    }
}
