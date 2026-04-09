<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\NewsSource;
use Illuminate\Http\Request;

class NewsSourceController extends Controller
{
    /**
     * Display a listing of the resource.
     */
    public function index()
    {
        $sources = NewsSource::orderBy('name')->paginate(20);

        return view('admin.news-sources.index', compact('sources'));
    }

    /**
     * Show the form for creating a new resource.
     */
    public function create()
    {
        return view('admin.news-sources.create');
    }

    /**
     * Store a newly created resource in storage.
     */
    public function store(Request $request)
    {
        $validated = $this->validateData($request);
        NewsSource::create($validated);

        return redirect()->route('admin.news-sources.index')->with('status', 'Sumber berita dibuat.');
    }

    /**
     * Display the specified resource.
     */
    public function show(NewsSource $newsSource)
    {
        //
    }

    /**
     * Show the form for editing the specified resource.
     */
    public function edit(NewsSource $newsSource)
    {
        return view('admin.news-sources.edit', compact('newsSource'));
    }

    /**
     * Update the specified resource in storage.
     */
    public function update(Request $request, NewsSource $newsSource)
    {
        $validated = $this->validateData($request);
        $newsSource->update($validated);

        return redirect()->route('admin.news-sources.index')->with('status', 'Sumber berita diperbarui.');
    }

    /**
     * Remove the specified resource from storage.
     */
    public function destroy(NewsSource $newsSource)
    {
        $newsSource->delete();

        return redirect()->route('admin.news-sources.index')->with('status', 'Sumber berita dihapus.');
    }

    protected function validateData(Request $request): array
    {
        $data = $request->validate([
            'name' => ['required', 'string'],
            'base_url' => ['nullable', 'url'],
            'type' => ['required', 'in:rss,api,manual,mock'],
            'is_active' => ['boolean'],
            'config_json' => ['nullable', 'array'],
        ]);

        $data['is_active'] = $request->boolean('is_active', true);

        return $data;
    }
}
