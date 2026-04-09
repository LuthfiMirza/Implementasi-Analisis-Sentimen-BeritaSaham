<x-app-layout>
    <div class="glass-card p-6">
        <div class="flex items-center justify-between mb-4">
            <div>
                <p class="text-xs text-slate-400 uppercase">Admin</p>
                <h1 class="text-2xl font-bold">Kelola Saham</h1>
            </div>
            <a href="{{ route('admin.stocks.create') }}" class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Tambah</a>
        </div>

        @if (session('status'))
            <div class="mb-3 text-green-400 text-sm">{{ session('status') }}</div>
        @endif

        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Kode</th>
                        <th class="px-4 py-3 text-left">Perusahaan</th>
                        <th class="px-4 py-3 text-left">Sektor</th>
                        <th class="px-4 py-3 text-left">Status</th>
                        <th class="px-4 py-3 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach($stocks as $stock)
                        <tr class="hover:bg-slate-900/60">
                            <td class="px-4 py-3 font-semibold">{{ $stock->code }}</td>
                            <td class="px-4 py-3 text-slate-300">{{ $stock->company_name }}</td>
                            <td class="px-4 py-3 text-slate-400">{{ $stock->sector }}</td>
                            <td class="px-4 py-3">
                                <span class="text-xs px-2 py-1 rounded-full {{ $stock->is_active ? 'bg-green-500/20 text-green-300' : 'bg-slate-800 text-slate-300' }}">
                                    {{ $stock->is_active ? 'Aktif' : 'Nonaktif' }}
                                </span>
                            </td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('admin.stocks.edit', $stock) }}" class="text-sky-400 text-xs">Edit</a>
                                <form action="{{ route('admin.stocks.destroy', $stock) }}" method="POST" class="inline">
                                    @csrf
                                    @method('DELETE')
                                    <button class="text-rose-400 text-xs" onclick="return confirm('Hapus saham ini?')">Hapus</button>
                                </form>
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>

        <div class="mt-4">
            {{ $stocks->links() }}
        </div>
    </div>
</x-app-layout>
