<x-app-layout>
    <div class="flex flex-col gap-4">
        <x-panel padding="p-6">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div>
                    <p class="text-xs uppercase text-slate-400">Berita Pasar</p>
                    <h1 class="text-2xl font-bold">Feed Terkini</h1>
                    <p class="text-sm text-slate-400">Filter emiten, sentimen, tanggal, sumber, metode, kualitas, dan urutkan berdasarkan kualitas tertinggi.</p>
                </div>
                <form method="GET" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3 w-full lg:w-auto">
                    <select name="code" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Semua Emiten</option>
                        @foreach($stocks as $stock)
                            <option value="{{ $stock->code }}" @selected($activeCode === $stock->code)>{{ $stock->code }} - {{ $stock->company_name }}</option>
                        @endforeach
                    </select>
                    <select name="sentiment" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Semua Sentimen</option>
                        <option value="positive" @selected(($filters['sentiment'] ?? '') === 'positive')>Positif</option>
                        <option value="neutral" @selected(($filters['sentiment'] ?? '') === 'neutral')>Netral</option>
                        <option value="negative" @selected(($filters['sentiment'] ?? '') === 'negative')>Negatif</option>
                    </select>
                    <select name="source" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Semua Sumber</option>
                        @foreach($sources as $source)
                            <option value="{{ $source->id }}" @selected(($filters['source'] ?? '') == $source->id)>{{ $source->name }}</option>
                        @endforeach
                    </select>
                    <select name="method" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Metode Sentimen</option>
                        <option value="python" @selected(($filters['method'] ?? '') === 'python')>Python</option>
                        <option value="rule_based" @selected(($filters['method'] ?? '') === 'rule_based')>Rule-based</option>
                        <option value="hybrid_fallback" @selected(($filters['method'] ?? '') === 'hybrid_fallback')>Hybrid fallback</option>
                    </select>
                    <select name="quality" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Quality</option>
                        <option value="high" @selected(($filters['quality'] ?? '') === 'high')>High</option>
                        <option value="medium" @selected(($filters['quality'] ?? '') === 'medium')>Medium</option>
                        <option value="low" @selected(($filters['quality'] ?? '') === 'low')>Low</option>
                    </select>
                    <select name="relevance" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="">Relevansi</option>
                        <option value="high" @selected(($filters['relevance'] ?? '') === 'high')>High</option>
                        <option value="medium" @selected(($filters['relevance'] ?? '') === 'medium')>Medium</option>
                        <option value="low" @selected(($filters['relevance'] ?? '') === 'low')>Low</option>
                    </select>
                    <input type="date" name="date" value="{{ $filters['date'] ?? '' }}" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                    <input type="text" name="q" value="{{ $filters['q'] ?? '' }}" placeholder="Cari judul..." class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                    <select name="sort" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        <option value="quality" @selected(($filters['sort'] ?? 'quality') === 'quality')>Sort: Kualitas + Terbaru</option>
                        <option value="recent" @selected(($filters['sort'] ?? '') === 'recent')>Sort: Terbaru</option>
                        <option value="sentiment" @selected(($filters['sort'] ?? '') === 'sentiment')>Sort: Skor Sentimen</option>
                        <option value="relevance" @selected(($filters['sort'] ?? '') === 'relevance')>Sort: Relevansi</option>
                    </select>
                    <div class="flex items-stretch">
                        <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold w-full">Terapkan</button>
                    </div>
                </form>
            </div>
        </x-panel>

        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            @forelse($articles as $article)
                <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/50 hover:border-slate-700">
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase text-slate-400">{{ $article->stock?->code ?? 'GEN' }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                <h3 class="font-semibold leading-tight mt-1">{{ $article->title }}</h3>
                                <p class="text-[12px] text-slate-500 mt-1">{{ $article->published_at?->format('d M Y H:i') }}</p>
                            </div>
                            <div class="flex flex-col items-end gap-1">
                                <x-sentiment-badge :label="$article->sentiment_label ?? 'neutral'" />
                                <span class="px-2 py-1 rounded-full text-[11px] border border-slate-700 bg-slate-800/50 text-slate-100">
                                    {{ $article->quality_band ? ucfirst($article->quality_band) : 'Quality?' }}
                                </span>
                            </div>
                        </div>
                    <p class="text-sm text-slate-300 mt-2">{{ \Illuminate\Support\Str::limit($article->summary ?? $article->content_snippet, 160) }}</p>
                    <div class="flex flex-wrap items-center justify-between mt-3 text-[12px] text-slate-400 gap-2">
                        <span>Skor: {{ $article->sentiment_score ?? '-' }} | Conf: {{ $article->sentiment_confidence ?? '-' }}</span>
                        <span class="px-2 py-1 rounded-full border border-slate-700 bg-slate-800/50">{{ $article->sentiment_method ?? 'rule_based' }}</span>
                        <span class="px-2 py-1 rounded-full border border-emerald-700/60 bg-emerald-900/30 text-emerald-100">Relevansi: {{ $article->relevance_band ?? '-' }}</span>
                        <span class="px-2 py-1 rounded-full border border-indigo-700/60 bg-indigo-900/30 text-indigo-100">Q: {{ $article->final_quality_score ?? '-' }}</span>
                        <a href="{{ $article->source_url }}" target="_blank" class="text-sky-400 hover:underline">Buka artikel</a>
                    </div>
                </div>
            @empty
                <x-panel padding="p-6" class="col-span-2">
                    <p class="text-sm text-slate-400">Tidak ada berita dengan filter ini. Coba ubah emiten, tanggal, atau metode sentimen.</p>
                </x-panel>
            @endforelse
        </div>

        <div>
            {{ $articles->links() }}
        </div>
    </div>
</x-app-layout>
