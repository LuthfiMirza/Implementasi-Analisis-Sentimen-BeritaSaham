<x-app-layout>
    <div class="glass-card p-6 space-y-4">
        <h1 class="text-2xl font-bold">Admin News</h1>
        @if (session('status'))
            <div class="text-green-400 text-sm">{{ session('status') }}</div>
        @endif
        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Judul</th>
                        <th class="px-4 py-3 text-left">Saham</th>
                        <th class="px-4 py-3 text-left">Sentimen</th>
                        <th class="px-4 py-3 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach($articles as $article)
                        <tr>
                            <td class="px-4 py-3">{{ $article->title }}</td>
                            <td class="px-4 py-3">{{ $article->stock?->code ?? 'Macro' }}</td>
                            <td class="px-4 py-3">{{ $article->sentiment_label ?? '-' }}</td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('admin.news.show', $article) }}" class="text-sky-400 text-xs">Lihat</a>
                                <form action="{{ route('admin.news.destroy', $article) }}" method="POST" class="inline">
                                    @csrf
                                    @method('DELETE')
                                    <button class="text-rose-400 text-xs" onclick="return confirm('Hapus berita ini?')">Hapus</button>
                                </form>
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
        {{ $articles->links() }}
    </div>
</x-app-layout>
