<x-app-layout>
    <div class="space-y-6">
        <div class="flex items-center justify-between gap-4">
            <div>
                <p class="text-xs uppercase text-slate-400">Predictions</p>
                <h1 class="text-2xl font-bold text-slate-100">Prediksi Saham {{ $stock?->code ?? '-' }}</h1>
            </div>
            <form method="GET">
                <select name="code" onchange="this.form.submit()" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100">
                    @foreach($stocks as $item)
                        <option value="{{ $item->code }}" @selected($stock?->id === $item->id)>{{ $item->code }} — {{ $item->company_name }}</option>
                    @endforeach
                </select>
            </form>
        </div>

        <x-panel class="p-4 border-sky-500/30 bg-sky-500/5">
            <div class="text-sm text-sky-100 leading-relaxed">
                Model prediksi adalah hasil riset skripsi yang diuji dengan walk-forward validation. Untuk 10 ticker resmi, Model Teknikal V6A mencapai directional accuracy ~40.5%, sedangkan Model Teknikal+Sentimen V6B menunjukkan peningkatan ~1-2% pada sebagian konfigurasi. Untuk BUMI/DEWA, model yang tampil adalah model khusus per-saham dan tidak digabung dengan V6A/V6B. Output ini bersifat estimasi indikatif untuk decision support, bukan rekomendasi investasi final atau jaminan hasil.
            </div>
        </x-panel>

        @if(! empty($retrainStatus))
            <x-panel class="p-4 border-slate-700/80">
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div>
                        <h2 class="text-sm font-semibold text-slate-100">Status Retrain Model Volatil</h2>
                        <p class="text-xs text-slate-400 mt-1">Read-only dari <code>storage/app/prediction/retrain_history.jsonl</code>. Jalankan manual: <code>php artisan prediction:retrain-volatile --dry-run</code> atau <code>--force</code>.</p>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="min-w-full text-xs text-slate-300">
                        <thead class="text-slate-500 uppercase">
                            <tr>
                                <th class="text-left py-2 pr-4">Model</th>
                                <th class="text-left py-2 pr-4">Terakhir</th>
                                <th class="text-left py-2 pr-4">Decision</th>
                                <th class="text-left py-2 pr-4">Old F1</th>
                                <th class="text-left py-2 pr-4">New F1</th>
                                <th class="text-left py-2 pr-4">Rows Baru</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            @foreach($retrainStatus as $model => $row)
                                <tr>
                                    <td class="py-2 pr-4 font-semibold text-slate-200">{{ $model }}</td>
                                    <td class="py-2 pr-4">{{ $row['timestamp'] ?? '-' }}</td>
                                    <td class="py-2 pr-4">{{ $row['decision'] ?? '-' }}</td>
                                    <td class="py-2 pr-4">{{ isset($row['old_macro_f1']) ? number_format((float) $row['old_macro_f1'], 4) : '-' }}</td>
                                    <td class="py-2 pr-4">{{ isset($row['new_macro_f1']) ? number_format((float) $row['new_macro_f1'], 4) : '-' }}</td>
                                    <td class="py-2 pr-4">{{ $row['rows_new_data'] ?? 0 }}</td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </x-panel>
        @endif

        @if(! empty($predictions))
            @php
                $cards = [
                    'technical' => [
                        'title' => 'Prediksi Teknikal',
                        'subtitle' => 'V6A Random Forest · technical-only',
                    ],
                    'technical_sentiment' => [
                        'title' => 'Prediksi Teknikal + Sentimen',
                        'subtitle' => 'V6B Logistic Regression · technical + berita',
                    ],
                    'bumi_technical' => [
                        'title' => 'Prediksi Teknikal BUMI',
                        'subtitle' => 'BUMI Random Forest · threshold fixed 2.7%',
                    ],
                    'dewa_regime' => [
                        'title' => 'Deteksi Rezim DEWA',
                        'subtitle' => 'DEWA Logistic Regression · move vs no_move, bukan arah harga',
                    ],
                    'dewa_technical' => [
                        'title' => 'Prediksi Arah DEWA',
                        'subtitle' => 'DEWA Logistic Regression · ATR threshold 0.5, sinyal arah lemah/moderat',
                    ],
                ];
            @endphp

            <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
                @foreach($cards as $variant => $meta)
                    @php
                        if (! array_key_exists($variant, $predictions)) {
                            continue;
                        }
                        $item = $predictions[$variant] ?? null;
                        $sentimentUnavailable = $variant === 'technical_sentiment'
                            && (($item['has_sufficient_sentiment_data'] ?? null) === false);
                        $isRegime = $variant === 'dewa_regime';
                        $direction = strtolower((string) ($item['predicted_direction'] ?? 'flat'));
                        $regime = strtolower((string) ($item['predicted_regime'] ?? 'no_move'));
                        $badge = match ($direction) {
                            'up' => 'bg-green-500/20 text-green-300',
                            'down' => 'bg-rose-500/20 text-rose-300',
                            default => 'bg-slate-700 text-slate-200',
                        };
                        if ($isRegime) {
                            $badge = $regime === 'move' ? 'bg-purple-500/20 text-purple-300' : 'bg-slate-700 text-slate-200';
                        }
                        $source = $item['model_source'] ?? 'unavailable';
                        $sourceBadge = $source === 'fallback_heuristic'
                            ? 'bg-amber-500/15 text-amber-300'
                            : 'bg-sky-500/15 text-sky-300';
                    @endphp

                    <x-panel class="p-6 space-y-5">
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <h2 class="text-lg font-semibold text-slate-100">{{ $meta['title'] }}</h2>
                                <p class="text-xs text-slate-400 mt-1">{{ $meta['subtitle'] }}</p>
                            </div>
                            <span class="px-3 py-1 rounded-full text-xs {{ $sourceBadge }}">
                                {{ $source }}
                            </span>
                        </div>

                        @if($sentimentUnavailable)
                            <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
                                <div class="text-amber-200 font-semibold">Data sentimen belum memadai</div>
                                <p class="text-sm text-amber-100/80 mt-1">
                                    {{ $item['message'] ?? 'Data sentimen berita untuk saham ini belum memadai pada periode ini. Gunakan Model Teknikal sebagai acuan indikatif.' }}
                                </p>
                            </div>
                        @elseif($item)
                            <div class="flex flex-wrap items-center gap-3">
                                <span class="px-3 py-1 rounded-full text-sm font-semibold {{ $badge }}">
                                    {{ $isRegime ? strtoupper($regime) : strtoupper($direction) }}
                                </span>
                                @if(! empty($item['model_name']))
                                    <span class="px-3 py-1 rounded-full text-xs bg-slate-700 text-slate-200">
                                        {{ $item['model_name'] }}
                                    </span>
                                @endif
                            </div>

                            <div>
                                <div class="text-xs uppercase text-slate-400">{{ $isRegime ? 'Regime Probability' : 'Probability' }}</div>
                                <div class="text-4xl font-bold text-slate-100">
                                    {{ number_format(((float) ($item['probability'] ?? 0)) * 100, 1) }}%
                                </div>
                            </div>

                            <div>
                                <div class="text-xs uppercase text-slate-400">Basis</div>
                                <p class="text-sm text-slate-300 mt-1">{{ $item['basis'] ?? '-' }}</p>
                            </div>

                            @if($variant === 'dewa_technical')
                                <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                                    Sinyal arah DEWA ini lemah/moderat: directional accuracy riset berada di bawah majority-class baseline pada sebagian pengujian. Gunakan sebagai pembanding, bukan sinyal final.
                                </div>
                            @endif

                            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                                <div class="rounded-lg border border-slate-800 p-3">
                                    <div class="text-green-300 font-semibold">Bullish</div>
                                    <p class="text-slate-400 mt-1">{{ $item['scenario_bullish'] ?? '-' }}</p>
                                </div>
                                <div class="rounded-lg border border-slate-800 p-3">
                                    <div class="text-slate-200 font-semibold">Neutral</div>
                                    <p class="text-slate-400 mt-1">{{ $item['scenario_neutral'] ?? '-' }}</p>
                                </div>
                                <div class="rounded-lg border border-slate-800 p-3">
                                    <div class="text-rose-300 font-semibold">Bearish</div>
                                    <p class="text-slate-400 mt-1">{{ $item['scenario_bearish'] ?? '-' }}</p>
                                </div>
                            </div>
                        @else
                            <div class="rounded-lg border border-slate-800 p-4 text-sm text-slate-300">
                                Prediction unavailable.
                            </div>
                        @endif
                    </x-panel>
                @endforeach
            </div>
        @elseif($prediction)
            <x-panel class="p-6 text-center text-slate-300">
                Prediction tersedia, tetapi format dual-model belum tersedia.
            </x-panel>
        @else
            <x-panel class="p-6 text-center text-slate-300">
                Prediction unavailable.
            </x-panel>
        @endif
    </div>
</x-app-layout>
