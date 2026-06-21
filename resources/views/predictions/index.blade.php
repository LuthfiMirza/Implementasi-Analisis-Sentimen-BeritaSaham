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
                Kedua model adalah hasil riset skripsi yang diuji dengan walk-forward validation. Model Teknikal mencapai directional accuracy ~40.5%, sedangkan Model Teknikal+Sentimen menunjukkan peningkatan ~1-2% pada sebagian konfigurasi pengujian. Output ini bersifat estimasi indikatif untuk decision support, bukan rekomendasi investasi final atau jaminan hasil.
            </div>
        </x-panel>

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
                ];
            @endphp

            <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
                @foreach($cards as $variant => $meta)
                    @php
                        $item = $predictions[$variant] ?? null;
                        $sentimentUnavailable = $variant === 'technical_sentiment'
                            && (($item['has_sufficient_sentiment_data'] ?? null) === false);
                        $direction = strtolower((string) ($item['predicted_direction'] ?? 'flat'));
                        $badge = match ($direction) {
                            'up' => 'bg-green-500/20 text-green-300',
                            'down' => 'bg-rose-500/20 text-rose-300',
                            default => 'bg-slate-700 text-slate-200',
                        };
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
                                    {{ strtoupper($direction) }}
                                </span>
                                @if(! empty($item['model_name']))
                                    <span class="px-3 py-1 rounded-full text-xs bg-slate-700 text-slate-200">
                                        {{ $item['model_name'] }}
                                    </span>
                                @endif
                            </div>

                            <div>
                                <div class="text-xs uppercase text-slate-400">Probability</div>
                                <div class="text-4xl font-bold text-slate-100">
                                    {{ number_format(((float) ($item['probability'] ?? 0)) * 100, 1) }}%
                                </div>
                            </div>

                            <div>
                                <div class="text-xs uppercase text-slate-400">Basis</div>
                                <p class="text-sm text-slate-300 mt-1">{{ $item['basis'] ?? '-' }}</p>
                            </div>

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
