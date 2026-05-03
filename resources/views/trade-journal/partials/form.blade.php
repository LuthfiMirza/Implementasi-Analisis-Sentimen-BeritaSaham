<div>
    <label class="block text-sm text-slate-300">Ticker</label>
    <input type="text" name="ticker" maxlength="10" value="{{ old('ticker', $trade?->ticker ?? $trade?->stock?->code) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
    @error('ticker') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
        <label class="block text-sm text-slate-300">Direction</label>
        <select name="direction" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
            <option value="long" @selected(old('direction', $trade?->direction ?? 'long') === 'long')>long</option>
            <option value="short" @selected(old('direction', $trade?->direction ?? 'long') === 'short')>short</option>
        </select>
        @error('direction') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
    </div>
    <div>
        <label class="block text-sm text-slate-300">Trade Date</label>
        <input type="date" name="trade_date" value="{{ old('trade_date', optional($trade?->trade_date ?? $trade?->entry_date)->format('Y-m-d') ?? now()->toDateString()) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
        @error('trade_date') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
    </div>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
        <label class="block text-sm text-slate-300">Entry Price</label>
        <input type="number" step="0.01" min="0" name="entry_price" value="{{ old('entry_price', $trade?->entry_price) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
        @error('entry_price') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
    </div>
    <div>
        <label class="block text-sm text-slate-300">Quantity</label>
        <input type="number" min="1" name="quantity" value="{{ old('quantity', $trade?->quantity ?? $trade?->lot_size ?? 1) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
        @error('quantity') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
    </div>
</div>

<div>
    <label class="block text-sm text-slate-300">Notes</label>
    <textarea name="notes" rows="3" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">{{ old('notes', $trade?->notes) }}</textarea>
    @error('notes') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
</div>
