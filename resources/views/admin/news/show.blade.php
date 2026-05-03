<x-app-layout>
    <div class="glass-card p-6 space-y-4">
        <a href="{{ route('admin.news.index') }}" class="text-xs text-sky-400">← Kembali</a>
        <h1 class="text-2xl font-bold">{{ $article->title }}</h1>
        <div class="text-sm text-slate-400">
            {{ $article->stock?->code ?? 'Macro' }} · {{ $article->source_provider ?? $article->source?->type ?? '-' }} · {{ optional($article->published_at)->format('d M Y') }}
        </div>
        <p class="text-slate-300">{{ $article->summary }}</p>
        <div class="text-sm">Sentimen: <span class="font-semibold">{{ $article->sentiment_label ?? '-' }}</span></div>
    </div>
</x-app-layout>
