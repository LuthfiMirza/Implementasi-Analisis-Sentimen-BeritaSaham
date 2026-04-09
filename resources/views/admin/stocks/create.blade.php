<x-app-layout>
    <div class="glass-card p-6">
        <h1 class="text-2xl font-bold mb-4">Tambah Saham</h1>
        <form action="{{ route('admin.stocks.store') }}" method="POST" class="space-y-4">
            @csrf
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-slate-300">Kode</label>
                    <input type="text" name="code" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Perusahaan</label>
                    <input type="text" name="company_name" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Sektor</label>
                    <input type="text" name="sector" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Exchange</label>
                    <input type="text" name="exchange" value="IDX" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">TradingView Symbol</label>
                    <input type="text" name="tradingview_symbol" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Yahoo Symbol</label>
                    <input type="text" name="yahoo_symbol" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
            </div>
            <div>
                <label class="block text-sm text-slate-300">Deskripsi</label>
                <textarea name="description" rows="3" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"></textarea>
            </div>
            <label class="inline-flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" name="is_active" value="1" class="rounded border-slate-700" checked> Aktif
            </label>
            <div class="flex gap-3">
                <a href="{{ route('admin.stocks.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>
</x-app-layout>
