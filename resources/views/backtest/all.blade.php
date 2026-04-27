<x-app-layout>
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div class="flex items-center justify-between gap-3">
            <div>
                <p class="text-xs uppercase text-slate-400">Backtest DSS</p>
                <h1 class="text-2xl font-bold text-slate-100">Backtest Semua Saham</h1>
                <p class="text-sm text-slate-400">Akurasi agregat prediksi DSS vs return {{ $forward }} hari</p>
            </div>
            <a href="{{ route('backtest.index') }}" class="text-xs text-sky-400 hover:underline">Pilih per saham →</a>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <x-panel class="p-4">
                <div class="text-xs uppercase text-slate-400">Overall Accuracy</div>
                <div class="text-3xl font-bold text-sky-400">{{ $summary['overall_accuracy'] ?? 0 }}%</div>
            </x-panel>
            <x-panel class="p-4">
                <div class="text-xs uppercase text-slate-400">Total Prediksi</div>
                <div class="text-3xl font-bold text-slate-100">{{ $summary['total_predictions'] ?? 0 }}</div>
            </x-panel>
            <x-panel class="p-4">
                <div class="text-xs uppercase text-slate-400">Forward Days</div>
                <div class="text-3xl font-bold text-slate-100">{{ $forward }}</div>
                <div class="text-xs text-slate-500">Threshold: {{ $threshold }}%</div>
            </x-panel>
        </div>

        <div class="text-xs text-slate-500">
            Halaman agregat memakai window terbaru agar evaluasi web tetap responsif.
        </div>

        <x-panel class="p-0 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm text-slate-200">
                    <thead class="bg-slate-900 text-xs uppercase text-slate-400">
                        <tr>
                            <th class="px-4 py-3 text-left">Saham</th>
                            <th class="px-4 py-3 text-left">Total</th>
                            <th class="px-4 py-3 text-left">Akurasi</th>
                            <th class="px-4 py-3 text-left">Korelasi</th>
                            <th class="px-4 py-3 text-left">Detail</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        @foreach($summary['per_stock'] ?? [] as $row)
                            @php
                                $acc = $row['accuracy'] ?? 0;
                                $color = $acc >= 60 ? 'text-green-400' : ($acc >= 40 ? 'text-amber-400' : 'text-rose-400');
                            @endphp
                            <tr class="hover:bg-slate-800/50">
                                <td class="px-4 py-2 font-semibold">{{ $row['code'] }}</td>
                                <td class="px-4 py-2">{{ $row['total'] }}</td>
                                <td class="px-4 py-2">
                                    <span class="{{ $color }}">{{ $acc }}%</span>
                                </td>
                                <td class="px-4 py-2 text-sky-300">{{ $row['correlation'] }}</td>
                                <td class="px-4 py-2">
                                    <a href="{{ route('backtest.index', ['code' => $row['code'], 'forward' => $forward, 'threshold' => $threshold, 'max_windows' => $maxWindows ?? 5]) }}"
                                       class="text-xs text-sky-400 hover:underline">Lihat</a>
                                </td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
        </x-panel>

        <div class="glass-card border border-slate-800/80 rounded-2xl p-5 mt-4">
            <h3 class="font-semibold text-slate-200 mb-3">
                📊 Ringkasan Evaluasi Model (Semua Saham)
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div>
                    <p class="text-xs text-slate-500 uppercase mb-1">Overall Accuracy</p>
                    <p class="text-2xl font-bold
                        {{ ($summary['overall_accuracy'] ?? 0) >= 60 ? 'text-green-400'
                           : (($summary['overall_accuracy'] ?? 0) >= 45 ? 'text-amber-400' : 'text-rose-400') }}">
                        {{ $summary['overall_accuracy'] ?? 0 }}%
                    </p>
                    <p class="text-xs text-slate-500 mt-1">
                        {{ $summary['total_correct'] ?? 0 }}/{{ $summary['total_predictions'] ?? 0 }} benar
                    </p>
                </div>
                <div class="md:col-span-2">
                    <p class="text-xs text-slate-500 uppercase mb-1">Konteks Pasar</p>
                    <p class="text-xs text-slate-400">
                        Periode backtest Jan-Apr 2026 ditandai oleh volatilitas tinggi
                        akibat kebijakan tariff global. IHSG turun ~16% selama periode ini.
                        Kondisi bearish ekstrem ini mempengaruhi akurasi semua model prediksi
                        jangka pendek berbasis analisis teknikal dan sentimen.
                    </p>
                </div>
            </div>
        </div>
    </div>
</x-app-layout>
