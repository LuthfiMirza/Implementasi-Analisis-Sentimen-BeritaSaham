<x-app-layout>
    <div class="glass-card p-6">
        <h1 class="text-2xl font-bold mb-4">Tambah Artikel</h1>
        <form action="{{ route('admin.news-articles.store') }}" method="POST" class="space-y-4">
            @csrf
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-slate-300">Judul</label>
                    <input type="text" name="title" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Slug</label>
                    <input type="text" name="slug" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">URL Sumber</label>
                    <input type="url" name="source_url" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Tanggal Publikasi</label>
                    <input type="datetime-local" name="published_at" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Emiten</label>
                    <select name="stock_id" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        <option value="">-</option>
                        @foreach($stocks as $stock)
                            <option value="{{ $stock->id }}">{{ $stock->code }} - {{ $stock->company_name }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Sumber</label>
                    <select name="news_source_id" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        <option value="">-</option>
                        @foreach($sources as $source)
                            <option value="{{ $source->id }}">{{ $source->name }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Sentimen</label>
                    <select name="sentiment_label" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        <option value="">Otomatis</option>
                        <option value="positive">Positive</option>
                        <option value="neutral">Neutral</option>
                        <option value="negative">Negative</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Skor</label>
                    <input type="number" step="0.01" min="-1" max="1" name="sentiment_score" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
            </div>
            <div>
                <label class="block text-sm text-slate-300">Ringkasan</label>
                <textarea name="summary" rows="3" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"></textarea>
            </div>
            <div class="flex gap-3">
                <a href="{{ route('admin.news-articles.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>
</x-app-layout>
