<x-app-layout>
    <div class="glass-card p-6 max-w-2xl">
        <h1 class="text-2xl font-bold mb-4">Tambah Trade Journal</h1>
        <form action="{{ route('trade-journal.store') }}" method="POST" class="space-y-4">
            @csrf
            @include('trade-journal.partials.form', ['trade' => null])
            <div class="flex gap-3">
                <a href="{{ route('trade-journal.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>
</x-app-layout>
