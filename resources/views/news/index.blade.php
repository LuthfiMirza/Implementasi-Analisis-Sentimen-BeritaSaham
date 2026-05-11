<x-app-layout>
    <div class="flex flex-col gap-4">
        <x-panel padding="p-6">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div>
                    <p class="text-xs uppercase text-slate-400">Berita Pasar</p>
                    <h1 class="text-2xl font-bold">
                        Feed Terkini
                        <span class="ml-2 text-sm font-normal text-slate-400">
                            {{ $articles->total() }} artikel
                        </span>
                    </h1>
                    <p class="text-sm text-slate-400">Filter emiten, sentimen, tanggal, sumber, metode, kualitas, dan urutkan berdasarkan kualitas atau tanggal berita.</p>
                </div>
                <form method="GET" class="w-full">
                    <div class="space-y-3 w-full">
                        <div class="flex flex-wrap gap-2 items-center">
                            <select name="code" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 min-w-[140px]">
                                <option value="">Semua Emiten</option>
                                @foreach($stocks as $stock)
                                    <option value="{{ $stock->code }}" @selected($activeCode === $stock->code)>{{ $stock->code }}</option>
                                @endforeach
                            </select>

                            <select name="sentiment" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="">Semua Sentimen</option>
                                <option value="positive" @selected(($filters['sentiment'] ?? '') === 'positive')>▲ Positif</option>
                                <option value="neutral" @selected(($filters['sentiment'] ?? '') === 'neutral')>◆ Netral</option>
                                <option value="negative" @selected(($filters['sentiment'] ?? '') === 'negative')>▼ Negatif</option>
                                <option value="unavailable" @selected(($filters['sentiment'] ?? '') === 'unavailable')>• Unavailable</option>
                            </select>

                            <select name="quality" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="">Semua Kualitas</option>
                                <option value="high" @selected(($filters['quality'] ?? '') === 'high')>★ High</option>
                                <option value="medium" @selected(($filters['quality'] ?? '') === 'medium')>◈ Medium</option>
                                <option value="low" @selected(($filters['quality'] ?? '') === 'low')>◇ Low</option>
                            </select>

                            <select name="sort" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="quality" @selected(($filters['sort'] ?? 'quality') === 'quality')>Sort: Kualitas</option>
                                <option value="date_desc" @selected(in_array(($filters['sort'] ?? ''), ['date_desc', 'recent'], true))>Sort: Tanggal Terbaru</option>
                                <option value="date_asc" @selected(($filters['sort'] ?? '') === 'date_asc')>Sort: Tanggal Terlama</option>
                                <option value="sentiment" @selected(($filters['sort'] ?? '') === 'sentiment')>Sort: Sentimen</option>
                            </select>

                            <button type="submit"
                                    class="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-900 font-semibold text-sm transition">
                                Terapkan
                            </button>

                            <button type="button"
                                    onclick="document.getElementById('advFilters').classList.toggle('hidden')"
                                    class="px-3 py-2 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-400 text-sm transition">
                                Filter lanjutan ▾
                            </button>
                        </div>

                        <div id="advFilters" class="hidden flex flex-wrap gap-2 items-center pt-1 border-t border-slate-800">
                            <select name="source" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="">Semua Sumber</option>
                                @foreach($sources as $source)
                                    <option value="{{ $source->id }}" @selected(($filters['source'] ?? '') == $source->id)>{{ $source->name }}</option>
                                @endforeach
                            </select>

                            <select name="method" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="">Metode Sentimen</option>
                                <option value="python" @selected(($filters['method'] ?? '') === 'python')>Python NLP</option>
                                <option value="python_unavailable" @selected(($filters['method'] ?? '') === 'python_unavailable')>Python Unavailable</option>
                                <option value="rule_based" @selected(($filters['method'] ?? '') === 'rule_based')>Rule-based</option>
                                <option value="hybrid_fallback" @selected(($filters['method'] ?? '') === 'hybrid_fallback')>Hybrid</option>
                            </select>

                            <select name="relevance" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                                <option value="">Relevansi</option>
                                <option value="high" @selected(($filters['relevance'] ?? '') === 'high')>High</option>
                                <option value="medium" @selected(($filters['relevance'] ?? '') === 'medium')>Medium</option>
                            </select>

                            <input type="date" name="date" value="{{ $filters['date'] ?? '' }}"
                                   class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">

                            <input type="text" name="q" value="{{ $filters['q'] ?? '' }}"
                                   placeholder="🔍 Cari judul..."
                                   class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 min-w-[200px]">
                        </div>
                    </div>
                </form>
            </div>
        </x-panel>

        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            @forelse($articles as $article)
                @php
                    $displaySentiment = ($article->sentiment_method ?? null) === 'python_unavailable'
                        ? 'unavailable'
                        : ($article->sentiment_label ?? 'neutral');
                @endphp
                <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/50 hover:border-slate-600 transition border-l-4
                    {{ ($displaySentiment === 'positive') ? 'border-l-green-500' : (($displaySentiment === 'negative') ? 'border-l-rose-500' : (($displaySentiment === 'unavailable') ? 'border-l-amber-400' : 'border-l-slate-600')) }}">
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase text-slate-400">{{ $article->stock?->code ?? 'GEN' }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                <h3 class="font-semibold leading-tight mt-1">{{ $article->title }}</h3>
                                <p class="text-[12px] text-slate-500 mt-1">{{ $article->published_at?->format('d M Y H:i') }}</p>
                            </div>
                            <div class="flex flex-col items-end gap-1">
                                <x-sentiment-badge :label="$displaySentiment" />
                                <span class="px-2 py-1 rounded-full text-[11px] border border-slate-700 bg-slate-800/50 text-slate-100">
                                    {{ $article->quality_band ? ucfirst($article->quality_band) : 'Quality?' }}
                                </span>
                            </div>
                        </div>
                    @if($article->ml_sentiment_label && $article->rule_sentiment_label)
                        <div class="flex flex-wrap gap-2 mt-2 text-[10px]">
                            <span class="px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-300">
                                ML: {{ ucfirst($article->ml_sentiment_label) }} ({{ round(($article->ml_confidence ?? 0) * 100) }}%)
                            </span>
                            <span class="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400">
                                Rule: {{ ucfirst($article->rule_sentiment_label) }}
                            </span>
                            @if($article->ml_rule_agree === false)
                                <span class="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                                    ⚡ Berbeda
                                </span>
                            @endif
                        </div>
                    @endif
                    <p class="text-sm text-slate-300 mt-2">{{ \Illuminate\Support\Str::limit($article->summary ?? $article->content_snippet, 160) }}</p>
                    <div class="flex flex-wrap items-center justify-between mt-3 text-[12px] text-slate-400 gap-2">
                        <span>Skor: {{ ($article->sentiment_method ?? null) === 'python_unavailable' ? 'unavailable' : ($article->sentiment_score ?? '-') }} | Conf: {{ ($article->sentiment_method ?? null) === 'python_unavailable' ? '-' : ($article->sentiment_confidence ?? '-') }}</span>
                        <span class="px-2 py-1 rounded-full border border-slate-700 bg-slate-800/50">{{ $article->sentiment_method ?? 'python_unavailable' }}</span>
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

        <div class="mt-6">
            <div class="flex flex-col items-center gap-3">
                <div class="text-xs text-slate-500">
                    Showing {{ $articles->firstItem() ?? 0 }} to {{ $articles->lastItem() ?? 0 }} of {{ $articles->total() }} results
                </div>
                <div class="bg-slate-900/80 border border-slate-800 rounded-xl shadow-lg shadow-slate-900/40 px-3 py-2">
                    {{ $articles->appends(request()->query())->onEachSide(1)->links('components.pagination-dark') }}
                </div>
            </div>
        </div>
    </div>
</x-app-layout>
