<?php

namespace App\Http\Controllers;

use App\Models\NewsArticle;
use App\Models\Stock;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Str;

class SearchController extends Controller
{
    public function __invoke(Request $request): JsonResponse
    {
        $query = trim((string) $request->query('q', ''));
        $types = $this->normalizeTypes($request->query('types', []));

        if ($query === '') {
            return response()->json([
                'query' => $query,
                'results' => $this->emptyResults(),
            ]);
        }

        $results = $this->emptyResults();

        if (in_array('stocks', $types, true)) {
            $results['stocks'] = $this->searchStocks($query);
        }

        if (in_array('news', $types, true)) {
            $results['news'] = $this->searchNews($query);
        }

        if (in_array('pages', $types, true)) {
            $results['pages'] = $this->searchPages($query);
        }

        if (in_array('actions', $types, true)) {
            $results['actions'] = $this->searchActions($query);
        }

        return response()->json([
            'query' => $query,
            'results' => $results,
        ]);
    }

    protected function normalizeTypes(mixed $types): array
    {
        $allowed = ['stocks', 'news', 'pages', 'actions'];
        $selected = collect(Arr::wrap($types))
            ->map(fn ($type) => (string) $type)
            ->filter(fn ($type) => in_array($type, $allowed, true))
            ->values()
            ->all();

        return $selected === [] ? $allowed : $selected;
    }

    protected function emptyResults(): array
    {
        return [
            'stocks' => [],
            'news' => [],
            'pages' => [],
            'actions' => [],
        ];
    }

    protected function searchStocks(string $query): array
    {
        return Stock::query()
            ->where('is_active', true)
            ->where(function ($builder) use ($query) {
                $builder->where('code', 'like', '%'.$query.'%')
                    ->orWhere('company_name', 'like', '%'.$query.'%');
            })
            ->orderByRaw('CASE WHEN code = ? THEN 0 WHEN code LIKE ? THEN 1 ELSE 2 END', [strtoupper($query), strtoupper($query).'%'])
            ->orderBy('code')
            ->limit(5)
            ->get(['id', 'code', 'company_name', 'sector', 'tradingview_symbol'])
            ->map(fn (Stock $stock) => [
                'type' => 'stock',
                'label' => 'Saham',
                'title' => $stock->code,
                'subtitle' => $stock->company_name,
                'meta' => $stock->sector,
                'url' => route('stocks.show', $stock->code, false),
                'tradingview_symbol' => $stock->tradingview_symbol,
            ])
            ->all();
    }

    protected function searchNews(string $query): array
    {
        return NewsArticle::query()
            ->with('source')
            ->where('title', 'like', '%'.$query.'%')
            ->latest('published_at')
            ->limit(5)
            ->get(['id', 'news_source_id', 'title', 'summary', 'source_provider', 'published_at'])
            ->map(fn (NewsArticle $article) => [
                'type' => 'news',
                'label' => 'Berita',
                'title' => $article->title,
                'subtitle' => Str::limit($article->summary ?: ($article->source?->name ?? $article->source_provider ?? 'Berita pasar'), 90),
                'meta' => $article->source?->name ?? $article->source_provider ?? $article->published_at?->format('d M Y') ?? 'Berita',
                'url' => route('news.index', ['q' => $query], false),
            ])
            ->all();
    }

    protected function searchPages(string $query): array
    {
        return collect($this->pages())
            ->filter(fn ($page) => Str::contains(Str::lower($page['title'].' '.$page['subtitle'].' '.$page['keywords']), Str::lower($query)))
            ->take(5)
            ->values()
            ->all();
    }

    protected function searchActions(string $query): array
    {
        $actions = collect($this->globalActions())
            ->filter(fn ($action) => Str::contains(Str::lower($action['title'].' '.$action['subtitle']), Str::lower($query)));

        $stock = Stock::query()
            ->where('is_active', true)
            ->where('code', strtoupper($query))
            ->first(['id', 'code', 'company_name']);

        if ($stock) {
            $actions = collect([
                [
                    'type' => 'action',
                    'label' => 'Aksi Cepat',
                    'title' => 'Buka dashboard '.$stock->code,
                    'subtitle' => $stock->company_name,
                    'meta' => 'Aksi',
                    'url' => route('stocks.show', $stock->code, false),
                ],
                [
                    'type' => 'action',
                    'label' => 'Aksi Cepat',
                    'title' => 'Buka prediksi '.$stock->code,
                    'subtitle' => 'Lihat analisis dan prediksi saham '.$stock->code,
                    'meta' => 'Aksi',
                    'url' => route('analytics.index', ['code' => $stock->code], false),
                ],
                [
                    'type' => 'action',
                    'label' => 'Aksi Cepat',
                    'title' => 'Lihat berita '.$stock->code,
                    'subtitle' => 'Filter berita terkait '.$stock->code,
                    'meta' => 'Aksi',
                    'url' => route('news.index', ['code' => $stock->code, 'q' => $stock->code], false),
                ],
                [
                    'type' => 'action',
                    'label' => 'Aksi Cepat',
                    'title' => 'Tambah '.$stock->code.' ke watchlist',
                    'subtitle' => 'Buka halaman watchlist untuk menambahkan saham',
                    'meta' => 'Aksi',
                    'url' => route('watchlist.index', ['add' => $stock->code], false),
                ],
            ])->merge($actions);
        }

        return $actions->take(5)->values()->all();
    }

    protected function pages(): array
    {
        return [
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Dashboard', 'subtitle' => 'Ringkasan pasar, grafik, berita, dan insight sentimen', 'meta' => 'Halaman', 'url' => route('dashboard', [], false), 'keywords' => 'home utama saham'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Watchlist', 'subtitle' => 'Pantau saham favorit dan ranking teknikal', 'meta' => 'Halaman', 'url' => route('watchlist.index', [], false), 'keywords' => 'favorit ranking teknikal'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Prediksi', 'subtitle' => 'Analisis harga, sentimen, dan prediksi saham', 'meta' => 'Halaman', 'url' => route('analytics.index', [], false), 'keywords' => 'prediction analytics analisis'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Evaluasi Model', 'subtitle' => 'Evaluasi performa prediksi dan model DSS', 'meta' => 'Halaman', 'url' => route('evaluasi.index', [], false), 'keywords' => 'akurasi model pengujian'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Audit Sentimen', 'subtitle' => 'Audit label sentimen berita terhadap baseline', 'meta' => 'Halaman', 'url' => route('evaluasi.sentimen', [], false), 'keywords' => 'sentimen evaluasi audit'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Backtest DSS', 'subtitle' => 'Simulasi historis sistem pendukung keputusan', 'meta' => 'Halaman', 'url' => route('backtest.index', [], false), 'keywords' => 'simulasi historis decision support'],
            ['type' => 'page', 'label' => 'Halaman', 'title' => 'Berita Terkini', 'subtitle' => 'Daftar berita saham dan hasil sentimen', 'meta' => 'Halaman', 'url' => route('news.index', [], false), 'keywords' => 'news artikel feed'],
        ];
    }

    protected function globalActions(): array
    {
        return [
            ['type' => 'action', 'label' => 'Aksi Cepat', 'title' => 'Watchlist Saya', 'subtitle' => 'Buka daftar saham favorit', 'meta' => 'Aksi', 'url' => route('watchlist.index', [], false)],
            ['type' => 'action', 'label' => 'Aksi Cepat', 'title' => 'Prediksi Saham', 'subtitle' => 'Buka analisis prediksi saham', 'meta' => 'Aksi', 'url' => route('analytics.index', [], false)],
            ['type' => 'action', 'label' => 'Aksi Cepat', 'title' => 'Berita Terkini', 'subtitle' => 'Buka feed berita pasar', 'meta' => 'Aksi', 'url' => route('news.index', [], false)],
            ['type' => 'action', 'label' => 'Aksi Cepat', 'title' => 'Evaluasi Model', 'subtitle' => 'Buka laporan evaluasi model', 'meta' => 'Aksi', 'url' => route('evaluasi.index', [], false)],
            ['type' => 'action', 'label' => 'Aksi Cepat', 'title' => 'Backtest DSS', 'subtitle' => 'Buka simulasi historis DSS', 'meta' => 'Aksi', 'url' => route('backtest.index', [], false)],
        ];
    }
}
