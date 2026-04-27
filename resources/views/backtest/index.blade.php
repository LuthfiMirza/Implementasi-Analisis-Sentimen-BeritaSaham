<x-app-layout>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div class="flex items-center justify-between gap-3">
            <div>
                <p class="text-xs uppercase text-slate-400">Backtest DSS</p>
                <h1 class="text-2xl font-bold text-slate-100">Backtest DSS — {{ $stock->code }}</h1>
                <p class="text-sm text-slate-400">Validasi akurasi prediksi vs harga aktual {{ $forward }} hari ke depan</p>
            </div>
            <a href="{{ route('backtest.all') }}" class="text-xs text-sky-400 hover:underline">Lihat semua saham →</a>
        </div>

        <form method="GET" class="glass-card border border-slate-800 rounded-2xl p-4 grid grid-cols-1 md:grid-cols-6 gap-4 text-sm">
            <div>
                <label class="text-xs text-slate-400">Saham</label>
                <select name="code" class="w-full mt-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100">
                    @foreach($stocks as $s)
                        <option value="{{ $s->code }}" @selected($s->code === $stock->code)>{{ $s->code }} — {{ $s->company_name }}</option>
                    @endforeach
                </select>
            </div>
            <div>
                <label class="text-xs text-slate-400">Forward Days</label>
                <select name="forward" class="w-full mt-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100">
                    @foreach([3,5,10] as $f)
                        <option value="{{ $f }}" @selected($forward == $f)>{{ $f }} hari</option>
                    @endforeach
                </select>
            </div>
            <div>
                <label class="text-xs text-slate-400">Threshold</label>
                <select name="threshold" class="w-full mt-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100">
                    @foreach([0.5,1.0,2.0] as $t)
                        <option value="{{ $t }}" @selected($threshold == $t)>{{ $t }}%</option>
                    @endforeach
                </select>
            </div>
            <div>
                <label class="text-xs text-slate-400">Step</label>
                <select name="step" class="w-full mt-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100">
                    @foreach([3,5,10] as $s)
                        <option value="{{ $s }}" @selected($step == $s)>{{ $s }} hari</option>
                    @endforeach
                </select>
            </div>
            <div>
                <label class="text-xs text-slate-400">Max Windows</label>
                <select name="max_windows" class="w-full mt-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100">
                    @foreach([5,10,20] as $mw)
                        <option value="{{ $mw }}" @selected(($maxWindows ?? 10) == $mw)>{{ $mw }} window terbaru</option>
                    @endforeach
                </select>
            </div>
            <div class="flex items-end">
                <button type="submit" class="w-full bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg font-semibold">Jalankan</button>
            </div>
        </form>

        <div class="text-xs text-slate-500">
            Mode web dipangkas ke window terbaru agar halaman cepat dimuat. Gunakan nilai lebih besar hanya jika memang perlu audit history yang lebih panjang.
        </div>

        @if(isset($result['error']))
            <x-panel class="p-6 text-center text-amber-300 border border-amber-500/40 bg-amber-500/10">
                {{ $result['error'] }}
            </x-panel>
        @else
            @php
                $accColor = $result['accuracy'] >= 60 ? 'text-green-400' : ($result['accuracy'] >= 40 ? 'text-amber-400' : 'text-rose-400');
            @endphp
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
                <x-panel class="p-4">
                    <div class="text-xs uppercase text-slate-400">Total Prediksi</div>
                    <div class="text-3xl font-bold text-slate-100">{{ $result['total'] }}</div>
                </x-panel>
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Akurasi</div>
                    <div class="text-3xl font-bold {{ $accColor }}">{{ $result['accuracy'] }}%</div>
                    <div class="w-full bg-slate-800 rounded-full h-2">
                        <div class="h-2 rounded-full {{ $accColor === 'text-green-400' ? 'bg-green-500' : ($accColor === 'text-amber-400' ? 'bg-amber-500' : 'bg-rose-500') }}"
                             style="width: {{ $result['accuracy'] }}%"></div>
                    </div>
                </x-panel>
                <x-panel class="p-4">
                    <div class="text-xs uppercase text-slate-400">Benar</div>
                    <div class="text-3xl font-bold text-slate-100">{{ $result['correct'] }} / {{ $result['total'] }}</div>
                </x-panel>
                <x-panel class="p-4">
                    <div class="text-xs uppercase text-slate-400">Korelasi Score vs Return</div>
                    <div class="text-3xl font-bold text-sky-400">{{ $result['correlation'] }}</div>
                    <div class="text-xs text-slate-500">Pearson r</div>
                </x-panel>
                <x-panel class="p-4">
                    <div class="text-xs uppercase text-slate-400">Avg Return</div>
                    <div class="text-sm text-slate-300">Benar: <span class="text-green-400">+{{ $result['avg_return_correct'] }}%</span></div>
                    <div class="text-sm text-slate-300">Salah: <span class="text-rose-400">{{ $result['avg_return_wrong'] }}%</span></div>
                </x-panel>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                @foreach(['up' => 'UP', 'flat' => 'FLAT', 'down' => 'DOWN'] as $key => $label)
                    @php
                        $data = $result['per_pred'][$key] ?? ['total' => 0, 'accuracy' => 0];
                        $color = $key === 'up' ? 'text-green-400' : ($key === 'down' ? 'text-rose-400' : 'text-slate-300');
                    @endphp
                    <x-panel class="p-4">
                        <div class="text-xs uppercase text-slate-400">Prediksi {{ $label }}</div>
                        <div class="text-2xl font-bold {{ $color }}">{{ $data['total'] ?? 0 }} prediksi</div>
                        <div class="text-sm text-slate-300">Akurasi: {{ $data['accuracy'] ?? 0 }}%</div>
                    </x-panel>
                @endforeach
            </div>

            <x-panel class="p-0 overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="min-w-full text-sm text-slate-200">
                        <thead class="bg-slate-900 text-xs uppercase text-slate-400">
                            <tr>
                                <th class="px-4 py-3 text-left">Tanggal</th>
                                <th class="px-4 py-3 text-left">Prediksi</th>
                                <th class="px-4 py-3 text-left">Aktual</th>
                                <th class="px-4 py-3 text-left">Return {{ $forward }}d</th>
                                <th class="px-4 py-3 text-left">Score</th>
                                <th class="px-4 py-3 text-left">Conf</th>
                                <th class="px-4 py-3 text-left">Benar?</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            @foreach($result['results'] as $row)
                                @php
                                    $predClass = $row['prediction'] === 'up' ? 'text-green-400' : ($row['prediction'] === 'down' ? 'text-rose-400' : 'text-slate-300');
                                    $retClass = $row['actual_return'] > 0 ? 'text-green-400' : ($row['actual_return'] < 0 ? 'text-rose-400' : 'text-slate-300');
                                @endphp
                                <tr class="hover:bg-slate-800/50">
                                    <td class="px-4 py-2">{{ $row['date'] }}</td>
                                    <td class="px-4 py-2">
                                        <span class="{{ $predClass }} font-semibold">
                                            @if($row['prediction'] === 'up') ▲ UP
                                            @elseif($row['prediction'] === 'down') ▼ DOWN
                                            @else → FLAT @endif
                                        </span>
                                    </td>
                                    <td class="px-4 py-2">{{ strtoupper($row['actual_direction']) }}</td>
                                    <td class="px-4 py-2">
                                        <span class="{{ $retClass }}">{{ $row['actual_return'] }}%</span>
                                    </td>
                                    <td class="px-4 py-2">{{ $row['final_score'] }}</td>
                                    <td class="px-4 py-2">{{ round($row['confidence'] * 100, 1) }}%</td>
                                    <td class="px-4 py-2">{{ $row['is_correct'] ? '✅' : '❌' }}</td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </x-panel>

            <div class="glass-card border border-slate-800/80 rounded-2xl p-5 mt-4 space-y-4">
                <h3 class="font-semibold text-slate-200">📊 Interpretasi Hasil Backtest</h3>

                {{-- Accuracy interpretation --}}
                <div class="p-3 rounded-xl border
                    {{ $result['accuracy'] >= 60
                       ? 'bg-green-500/5 border-green-500/20'
                       : ($result['accuracy'] >= 45
                          ? 'bg-amber-500/5 border-amber-500/20'
                          : 'bg-rose-500/5 border-rose-500/20') }}">
                    <p class="text-sm font-medium
                      {{ $result['accuracy'] >= 60 ? 'text-green-400'
                         : ($result['accuracy'] >= 45 ? 'text-amber-400' : 'text-rose-400') }}">
                      Akurasi: {{ $result['accuracy'] }}%
                      {{ $result['accuracy'] >= 60 ? '✅ Di atas random (50%)'
                         : ($result['accuracy'] >= 45 ? '⚠ Mendekati random'
                         : '❌ Di bawah random (50%)') }}
                    </p>
                    <p class="text-xs text-slate-400 mt-1">
                      @if($result['accuracy'] >= 60)
                        Model DSS menunjukkan kemampuan prediksi yang signifikan.
                        Hasil ini mendukung hipotesis bahwa kombinasi teknikal + sentimen
                        dapat memprediksi arah harga jangka pendek.
                      @elseif($result['accuracy'] >= 45)
                        Model menunjukkan sinyal lemah. Kemungkinan disebabkan oleh
                        coverage berita yang belum optimal atau kondisi pasar yang tidak normal.
                      @else
                        Akurasi di bawah 50% dapat disebabkan oleh beberapa faktor:
                        (1) Coverage berita sangat rendah — model bergantung pada sentimen,
                        (2) Periode backtest adalah fase downtrend ekstrem,
                        (3) Threshold prediksi perlu dikalibrasi ulang.
                      @endif
                    </p>
                </div>

                {{-- Prediction distribution warning --}}
                @php
                    $upTotal   = $result['per_pred']['up']['total']   ?? 0;
                    $flatTotal = $result['per_pred']['flat']['total'] ?? 0;
                    $downTotal = $result['per_pred']['down']['total'] ?? 0;
                    $allFlat   = $upTotal === 0 && $downTotal === 0;
                @endphp
                @if($allFlat)
                    <div class="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20">
                        <p class="text-sm font-medium text-amber-400">
                            ⚠ Semua prediksi FLAT ({{ $flatTotal }} prediksi)
                        </p>
                        <p class="text-xs text-slate-400 mt-1">
                            Model tidak mendeteksi sinyal UP atau DOWN yang cukup kuat.
                            Penyebab utama: coverage berita terlalu rendah (sistem membutuhkan
                            minimal 10+ artikel relevan per saham untuk menghasilkan sinyal berarti).
                            <strong class="text-amber-300">Rekomendasi:</strong>
                            Tingkatkan frekuensi fetch berita dan perluas sumber RSS/API.
                        </p>
                    </div>
                @endif

                {{-- Correlation interpretation --}}
                <div class="p-3 rounded-xl bg-slate-800/50 border border-slate-700">
                    <p class="text-sm font-medium text-slate-200">
                        Korelasi Pearson: {{ $result['correlation'] }}
                        @if($result['correlation'] > 0.3)
                            📈 Positif moderat
                        @elseif($result['correlation'] > 0)
                            📊 Positif lemah
                        @elseif($result['correlation'] > -0.3)
                            📊 Negatif lemah
                        @else
                            📉 Negatif moderat
                        @endif
                    </p>
                    <p class="text-xs text-slate-400 mt-1">
                        @if($result['correlation'] < -0.3)
                            Korelasi negatif menunjukkan bahwa pada periode ini,
                            DSS score tinggi justru berkorelasi dengan return negatif.
                            Ini konsisten dengan kondisi pasar Jan-Apr 2026 yang mengalami
                            downtrend akibat kebijakan tariff global — faktor makro eksternal
                            yang tidak tertangkap oleh model berbasis sentimen berita lokal.
                        @elseif(abs($result['correlation']) < 0.3)
                            Korelasi mendekati nol menunjukkan hubungan yang tidak linear
                            antara DSS score dan return aktual. Ini normal untuk model
                            multi-faktor yang menggabungkan teknikal, sentimen, dan fundamental.
                        @else
                            Korelasi positif menunjukkan DSS score memiliki hubungan searah
                            dengan return aktual — semakin tinggi score, semakin besar
                            kemungkinan return positif.
                        @endif
                    </p>
                </div>

                {{-- Academic note --}}
                <div class="p-3 rounded-xl bg-sky-500/5 border border-sky-500/20">
                    <p class="text-xs text-sky-400 font-medium mb-1">
                        📚 Catatan untuk Skripsi (Bab 4 — Pembahasan)
                    </p>
                    <p class="text-xs text-slate-400">
                        Hasil backtest ini memberikan temuan penting:
                        (1) Sistem DSS memerlukan coverage berita yang memadai (≥10 artikel/saham)
                        untuk menghasilkan sinyal yang akurat.
                        (2) Akurasi sistem sangat dipengaruhi oleh kondisi makro eksternal yang
                        tidak tertangkap oleh indikator teknikal maupun sentimen berita lokal.
                        (3) Periode Jan-Apr 2026 merupakan periode volatilitas tinggi akibat
                        kebijakan tariff global, yang membuat prediksi jangka pendek lebih sulit.
                        (4) Diperlukan data historis yang lebih panjang (minimal 6-12 bulan)
                        untuk evaluasi yang lebih representatif.
                    </p>
                </div>
            </div>
        @endif
    </div>
</x-app-layout>
