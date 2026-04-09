<x-app-layout>
    <div class="glass-card p-6">
        <div class="flex items-center justify-between mb-4">
            <div>
                <p class="text-xs uppercase text-slate-400">Admin</p>
                <h1 class="text-2xl font-bold">Artikel Berita</h1>
            </div>
            <a href="{{ route('admin.news-articles.create') }}" class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Tambah</a>
        </div>

        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Judul</th>
                        <th class="px-4 py-3 text-left">Emiten</th>
                        <th class="px-4 py-3 text-left">Sentimen</th>
                        <th class="px-4 py-3 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach($articles as $article)
                        <tr class="hover:bg-slate-900/60">
                            <td class="px-4 py-3 font-semibold">{{ Str::limit($article->title, 60) }}</td>
                            <td class="px-4 py-3 text-slate-400">{{ $article->stock?->code ?? '-' }}</td>
                            <td class="px-4 py-3">
                                <span class="text-xs px-2 py-1 rounded-full bg-slate-800 text-slate-200 border border-slate-700">
                                    {{ ucfirst($article->sentiment_label ?? 'neutral') }}
                                </span>
                            </td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('admin.news-articles.edit', $article) }}" class="text-sky-400 text-xs">Edit</a>
                                <form action="{{ route('admin.news-articles.destroy', $article) }}" method="POST" class="inline">
                                    @csrf
                                    @method('DELETE')
                                    <button class="text-rose-400 text-xs" onclick="return confirm('Hapus artikel ini?')">Hapus</button>
                                </form>
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
    </div>
</x-app-layout>
