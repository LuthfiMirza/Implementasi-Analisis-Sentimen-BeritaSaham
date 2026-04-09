<x-app-layout>
    <div class="glass-card p-6">
        <h1 class="text-2xl font-bold mb-4">Tambah Sumber Berita</h1>
        <form action="{{ route('admin.news-sources.store') }}" method="POST" class="space-y-4">
            @csrf
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-slate-300">Nama</label>
                    <input type="text" name="name" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Tipe</label>
                    <select name="type" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        <option value="rss">RSS</option>
                        <option value="api">API</option>
                        <option value="manual">Manual</option>
                        <option value="mock">Mock</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Base URL</label>
                    <input type="url" name="base_url" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
            </div>
            <label class="inline-flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" name="is_active" value="1" class="rounded border-slate-700" checked> Aktif
            </label>
            <div class="flex gap-3">
                <a href="{{ route('admin.news-sources.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>
</x-app-layout>
