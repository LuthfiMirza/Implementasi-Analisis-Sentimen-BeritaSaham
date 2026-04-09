<x-app-layout>
    <div class="glass-card p-6">
        <div class="flex items-center justify-between mb-4">
            <div>
                <p class="text-xs uppercase text-slate-400">Admin</p>
                <h1 class="text-2xl font-bold">Sumber Berita</h1>
            </div>
            <a href="{{ route('admin.news-sources.create') }}" class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Tambah</a>
        </div>

        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Nama</th>
                        <th class="px-4 py-3 text-left">Tipe</th>
                        <th class="px-4 py-3 text-left">Status</th>
                        <th class="px-4 py-3 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach($sources as $source)
                        <tr class="hover:bg-slate-900/60">
                            <td class="px-4 py-3 font-semibold">{{ $source->name }}</td>
                            <td class="px-4 py-3 text-slate-400">{{ strtoupper($source->type) }}</td>
                            <td class="px-4 py-3">
                                <span class="text-xs px-2 py-1 rounded-full {{ $source->is_active ? 'bg-green-500/20 text-green-300' : 'bg-slate-800 text-slate-300' }}">
                                    {{ $source->is_active ? 'Aktif' : 'Nonaktif' }}
                                </span>
                            </td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('admin.news-sources.edit', $source) }}" class="text-sky-400 text-xs">Edit</a>
                                <form action="{{ route('admin.news-sources.destroy', $source) }}" method="POST" class="inline">
                                    @csrf
                                    @method('DELETE')
                                    <button class="text-rose-400 text-xs" onclick="return confirm('Hapus sumber ini?')">Hapus</button>
                                </form>
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
    </div>
</x-app-layout>
