<x-app-layout>
    <div class="glass-card p-6">
        <h1 class="text-2xl font-bold mb-4">Edit Saham {{ $stock->code }}</h1>
        @if(session('status'))
            <div class="mb-4 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-300">
                {{ session('status') }}
            </div>
        @endif
        <form action="{{ route('admin.stocks.update', $stock) }}" method="POST" class="space-y-4">
            @csrf
            @method('PUT')
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-slate-300">Kode</label>
                    <input type="text" name="code" value="{{ $stock->code }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Perusahaan</label>
                    <input type="text" name="company_name" value="{{ $stock->company_name }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Sektor</label>
                    <input type="text" name="sector" value="{{ $stock->sector }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Exchange</label>
                    <input type="text" name="exchange" value="{{ $stock->exchange }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">TradingView Symbol</label>
                    <input type="text" name="tradingview_symbol" value="{{ $stock->tradingview_symbol }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Yahoo Symbol</label>
                    <input type="text" name="yahoo_symbol" value="{{ $stock->yahoo_symbol }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                </div>
            </div>
            <div>
                <label class="block text-sm text-slate-300">Deskripsi</label>
                <textarea name="description" rows="3" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">{{ $stock->description }}</textarea>
            </div>
            <label class="inline-flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" name="is_active" value="1" class="rounded border-slate-700" {{ $stock->is_active ? 'checked' : '' }}> Aktif
            </label>
            <div class="flex gap-3">
                <a href="{{ route('admin.stocks.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>

    <div class="glass-card p-6 mt-6">
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
            <div>
                <h2 class="text-xl font-bold">Update Fundamental Manual</h2>
                <p class="text-sm text-slate-400 mt-1">
                    Update hanya kolom PBV, PER, ROE, DER, EPS, Div Yield, dan tanggal snapshot. Tidak mengubah data harga, prediksi, atau model.
                </p>
            </div>
            <span class="inline-flex w-fit rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-200">
                Snapshot saat ini: {{ $stock->fundamentals_updated_at ? $stock->fundamentals_updated_at->format('d M Y') : 'tidak diketahui' }}
            </span>
        </div>

        <form action="{{ route('admin.stocks.fundamental.update', $stock) }}" method="POST" class="space-y-4">
            @csrf
            @method('PATCH')
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                    <label class="block text-sm text-slate-300">PBV</label>
                    <input type="number" step="0.01" name="pbv" value="{{ old('pbv', $stock->pbv) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('pbv')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">PER</label>
                    <input type="number" step="0.01" name="per" value="{{ old('per', $stock->per) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('per')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">ROE (%)</label>
                    <input type="number" step="0.01" name="roe" value="{{ old('roe', $stock->roe) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('roe')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">DER</label>
                    <input type="number" step="0.01" name="der" value="{{ old('der', $stock->der) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('der')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">EPS</label>
                    <input type="number" step="0.01" name="eps" value="{{ old('eps', $stock->eps) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('eps')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Div Yield (%)</label>
                    <input type="number" step="0.01" name="dividend_yield" value="{{ old('dividend_yield', $stock->dividend_yield) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                    @error('dividend_yield')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Tanggal Snapshot</label>
                    <input type="date" name="fundamentals_updated_at" value="{{ old('fundamentals_updated_at', optional($stock->fundamentals_updated_at)->toDateString() ?? now()->toDateString()) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                    @error('fundamentals_updated_at')<p class="mt-1 text-xs text-rose-400">{{ $message }}</p>@enderror
                </div>
            </div>
            <div class="flex gap-3">
                <button class="px-4 py-2 rounded-lg bg-amber-400 text-slate-950 font-semibold">Simpan Fundamental</button>
            </div>
        </form>
    </div>
</x-app-layout>
