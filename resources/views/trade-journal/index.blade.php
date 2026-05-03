<x-app-layout>
    <div class="glass-card p-6 space-y-4">
        <div class="flex items-center justify-between">
            <div>
                <p class="text-xs text-slate-400 uppercase">Trade Journal</p>
                <h1 class="text-2xl font-bold">Jurnal Trading</h1>
            </div>
            <a href="{{ route('trade-journal.create') }}" class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Tambah Trade</a>
        </div>

        @if (session('status'))
            <div class="text-green-400 text-sm">{{ session('status') }}</div>
        @endif
        @if (session('error'))
            <div class="text-rose-400 text-sm">{{ session('error') }}</div>
        @endif

        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Ticker</th>
                        <th class="px-4 py-3 text-left">Direction</th>
                        <th class="px-4 py-3 text-right">Entry</th>
                        <th class="px-4 py-3 text-right">Exit</th>
                        <th class="px-4 py-3 text-right">P&L</th>
                        <th class="px-4 py-3 text-left">Status</th>
                        <th class="px-4 py-3 text-left">Trade Date</th>
                        <th class="px-4 py-3 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @forelse($trades as $trade)
                        <tr class="hover:bg-slate-900/60">
                            <td class="px-4 py-3 font-semibold">{{ $trade->ticker ?? $trade->stock?->code }}</td>
                            <td class="px-4 py-3">{{ $trade->direction ?? 'long' }}</td>
                            <td class="px-4 py-3 text-right">{{ number_format((float) $trade->entry_price, 2) }}</td>
                            <td class="px-4 py-3 text-right">{{ $trade->exit_price !== null ? number_format((float) $trade->exit_price, 2) : '-' }}</td>
                            <td class="px-4 py-3 text-right {{ ($trade->pnl ?? $trade->pnl_total ?? 0) >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                                {{ ($trade->pnl ?? $trade->pnl_total) !== null ? number_format((float) ($trade->pnl ?? $trade->pnl_total), 2) : '-' }}
                            </td>
                            <td class="px-4 py-3">{{ $trade->status }}</td>
                            <td class="px-4 py-3">{{ optional($trade->trade_date ?? $trade->entry_date)->format('Y-m-d') }}</td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('trade-journal.edit', $trade) }}" class="text-sky-400 text-xs">Edit</a>
                                @if($trade->status !== 'closed')
                                    <form action="{{ route('trade-journal.close', $trade) }}" method="POST" class="inline-flex gap-1 items-center">
                                        @csrf
                                        @method('PATCH')
                                        <input type="number" step="0.01" min="0" name="exit_price" placeholder="Exit" class="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs">
                                        <button class="text-emerald-400 text-xs">Close</button>
                                    </form>
                                @endif
                                <form action="{{ route('trade-journal.destroy', $trade) }}" method="POST" class="inline">
                                    @csrf
                                    @method('DELETE')
                                    <button class="text-rose-400 text-xs" onclick="return confirm('Hapus trade ini?')">Delete</button>
                                </form>
                            </td>
                        </tr>
                    @empty
                        <tr>
                            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Belum ada trade journal.</td>
                        </tr>
                    @endforelse
                </tbody>
            </table>
        </div>

        {{ $trades->links() }}
    </div>
</x-app-layout>
