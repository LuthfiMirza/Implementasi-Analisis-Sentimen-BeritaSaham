<x-app-layout>
    @php
        $lag = $analytics['lag_correlations'] ?? ['h1' => null, 'h3' => null, 'h7' => null];
        $events = $analytics['event_study'] ?? ['positive_events' => [], 'negative_events' => []];
        $volumeImpact = $analytics['volume_impact'] ?? ['correlation' => null, 'peak_volume_dates' => []];
    @endphp

    <div class="flex flex-col gap-6">
        <x-panel padding="p-6">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div class="space-y-2">
                    <p class="text-xs uppercase text-slate-400">Analytics & Prediksi</p>
                    <div class="flex flex-wrap items-center gap-3">
                        <h1 class="text-3xl font-bold">{{ $stock->code }} • {{ $stock->company_name }}</h1>
                        <span class="text-[12px] px-3 py-1 rounded-full border border-slate-700 bg-slate-900/60">
                            {{ $decision['status'] }} • {{ $decision['confidence'] }}
                        </span>
                        <span class="text-[12px] px-3 py-1 rounded-full border border-slate-700 bg-slate-900/60">
                            Prediksi: {{ strtoupper($prediction['predicted_direction']) }} ({{ $prediction['confidence'] }})
                        </span>
                    </div>
                    <div class="flex flex-wrap items-center gap-4 text-sm text-slate-400">
                        <span>Harga: {{ $latestPrice?->close ? number_format($latestPrice->close, 2) : '-' }}</span>
                        <span class="{{ ($priceChange ?? 0) >=0 ? 'text-green-400' : 'text-rose-400' }}">Δ {{ $priceChange ? number_format($priceChange, 2) : '0.00' }}%</span>
                        <span>Sentimen rata-rata: {{ $analytics['average_sentiment'] }}</span>
                        <span>Artikel: {{ $summary['total'] }}</span>
                    </div>
                </div>
                <form method="GET" class="flex flex-wrap items-center gap-3">
                    <select name="code" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        @foreach($stocks as $item)
                            <option value="{{ $item->code }}" @selected($item->id === $stock->id)>{{ $item->code }} - {{ $item->company_name }}</option>
                        @endforeach
                    </select>
                    <select name="period" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        @foreach([7,30,90] as $p)
                            <option value="{{ $p }}" @selected($period === $p)>{{ $p }} hari</option>
                        @endforeach
                    </select>
                    <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Terapkan</button>
                </form>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3 mt-4">
                <x-metric-card label="Sentimen Avg" :value="$analytics['average_sentiment']" hint="Rata-rata periode" />
                <x-metric-card label="Weighted Sentiment" :value="$analytics['weighted_sentiment']" hint="Bobot sumber/headline/recency" />
                <x-metric-card label="Berita" :value="$analytics['news_volume']" hint="volume periode" />
                <x-metric-card label="Cumulative Return" :value="is_null($analytics['cumulative_return']) ? 'N/A' : $analytics['cumulative_return'].'%'" />
                <x-metric-card label="Volatilitas" :value="is_null($analytics['volatility']) ? 'N/A' : $analytics['volatility'].'%'" />
                <x-metric-card label="Same-day Corr" :value="is_null($analytics['same_day_correlation']) ? 'N/A' : $analytics['same_day_correlation']" hint="Sentimen vs return" />
            </div>
        </x-panel>

        <div class="grid grid-cols-12 gap-6">
            <div class="col-span-12 xl:col-span-8 space-y-5">
                <x-panel padding="p-6">
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            <p class="text-xs uppercase text-slate-400">Harga & Sentimen</p>
                            <h3 class="font-semibold">Overlay Harga, Sentimen, Volume</h3>
                        </div>
                        <div class="text-[11px] text-slate-400">Marker ⬆︎ event sentimen tinggi</div>
                    </div>
                    @if(($chartData['prices'] ?? collect())->filter()->count() === 0)
                        <p class="text-sm text-slate-400">Data harga atau sentimen belum tersedia untuk periode ini.</p>
                    @else
                        <canvas id="priceSentimentChart" class="h-80"></canvas>
                    @endif
                </x-panel>

                <x-panel padding="p-6">
                    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-3">
                        <div>
                            <p class="text-xs uppercase text-slate-400">Model Pendukung Keputusan</p>
                            <h3 class="font-semibold">{{ $decision['status'] }} • {{ $decision['confidence'] }} • Skor {{ $decision['final_score'] }}</h3>
                        </div>
                        <div class="text-xs text-slate-400">Bobot: Sentimen 35% • Tren 30% • Momentum 20% • Volume Berita 15%</div>
                    </div>
                    <p class="text-slate-200 leading-relaxed">{{ $decision['narrative'] }}</p>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                        <x-metric-card label="Return Periode" :value="is_null($decision['price_return']) ? 'N/A' : $decision['price_return'].'%'" />
                        <x-metric-card label="Momentum" :value="$decision['momentum_signal']" />
                        <x-metric-card label="MA Gap" :value="is_null($decision['technical']['ma_gap'] ?? null) ? 'N/A' : number_format(($decision['technical']['ma_gap'])*100,2).'%' " />
                        <x-metric-card label="RSI" :value="$decision['technical']['rsi'] ?? 'N/A'" />
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <div>
                            <p class="text-xs uppercase text-green-400 mb-2">Faktor Pendukung</p>
                            <ul class="space-y-2 text-sm text-slate-200">
                                @forelse($decision['supporting_factors'] as $item)
                                    <li class="flex items-start gap-2"><span class="mt-1 h-1.5 w-1.5 rounded-full bg-green-400"></span><span>{{ $item }}</span></li>
                                @empty
                                    <li class="text-slate-400">Belum ada.</li>
                                @endforelse
                            </ul>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-amber-400 mb-2">Faktor Pelemah</p>
                            <ul class="space-y-2 text-sm text-slate-200">
                                @forelse($decision['weakening_factors'] as $item)
                                    <li class="flex items-start gap-2"><span class="mt-1 h-1.5 w-1.5 rounded-full bg-amber-400"></span><span>{{ $item }}</span></li>
                                @empty
                                    <li class="text-slate-400">Belum ada.</li>
                                @endforelse
                            </ul>
                        </div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <div>
                            <p class="text-xs uppercase text-rose-400 mb-2">Risk Factors</p>
                            <ul class="space-y-2 text-sm text-slate-200">
                                @forelse($decision['risk_factors'] as $item)
                                    <li class="flex items-start gap-2"><span class="mt-1 h-1.5 w-1.5 rounded-full bg-rose-400"></span><span>{{ $item }}</span></li>
                                @empty
                                    <li class="text-slate-400">Belum ada.</li>
                                @endforelse
                            </ul>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-slate-400 mb-2">Aturan Invalidation</p>
                            <ul class="space-y-2 text-sm text-slate-200">
                                @forelse($decision['invalidation_rules'] as $item)
                                    <li class="flex items-start gap-2"><span class="mt-1 h-1.5 w-1.5 rounded-full bg-slate-400"></span><span>{{ $item }}</span></li>
                                @empty
                                    <li class="text-slate-400">Belum ada.</li>
                                @endforelse
                            </ul>
                        </div>
                    </div>
                </x-panel>

                <x-panel padding="p-6">
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            <p class="text-xs uppercase text-slate-400">Pengaruh Sentimen ke Harga</p>
                            <h3 class="font-semibold">Korelasi & Event Study</h3>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <x-metric-card label="Lag H+1" :value="is_null($lag['h1']) ? 'N/A' : $lag['h1']" />
                        <x-metric-card label="Lag H+3" :value="is_null($lag['h3']) ? 'N/A' : $lag['h3']" />
                        <x-metric-card label="Lag H+7" :value="is_null($lag['h7']) ? 'N/A' : $lag['h7']" />
                        <x-metric-card label="Volume→Volatilitas" :value="is_null($volumeImpact['correlation']) ? 'N/A' : $volumeImpact['correlation']" hint="korelasi volume berita vs |return|" />
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm text-slate-200">
                        <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/50">
                            <p class="text-xs uppercase text-green-400 mb-2">Event Positif</p>
                            <p class="text-sm text-slate-300">Jumlah: {{ count($events['positive_events'] ?? []) }}</p>
                            @if(($events['positive_events'] ?? []))
                                <p class="text-xs text-slate-400 mt-1">Contoh impact H+1/H+3/H+7: {{ data_get($events['positive_events'], '0.impact.h1') ?? 'n/a' }}% / {{ data_get($events['positive_events'], '0.impact.h3') ?? 'n/a' }}% / {{ data_get($events['positive_events'], '0.impact.h7') ?? 'n/a' }}%</p>
                            @endif
                        </div>
                        <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/50">
                            <p class="text-xs uppercase text-rose-400 mb-2">Event Negatif</p>
                            <p class="text-sm text-slate-300">Jumlah: {{ count($events['negative_events'] ?? []) }}</p>
                            @if(($events['negative_events'] ?? []))
                                <p class="text-xs text-slate-400 mt-1">Contoh impact H+1/H+3/H+7: {{ data_get($events['negative_events'], '0.impact.h1') ?? 'n/a' }}% / {{ data_get($events['negative_events'], '0.impact.h3') ?? 'n/a' }}% / {{ data_get($events['negative_events'], '0.impact.h7') ?? 'n/a' }}%</p>
                            @endif
                        </div>
                    </div>
                </x-panel>

                <x-panel padding="p-6">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-semibold">Skenario & Prediksi</h3>
                        <span class="text-[11px] text-slate-400">Prediksi indikatif, bukan rekomendasi.</span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/60">
                            <p class="text-xs uppercase text-green-400">Bullish</p>
                            <p class="font-semibold mt-1">{{ $decision['scenarios']['bullish'] }}</p>
                            <p class="text-xs text-slate-400 mt-2">{{ $prediction['scenario_bullish'] }}</p>
                        </div>
                        <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/60">
                            <p class="text-xs uppercase text-amber-400">Netral</p>
                            <p class="font-semibold mt-1">{{ $decision['scenarios']['neutral'] }}</p>
                            <p class="text-xs text-slate-400 mt-2">{{ $prediction['scenario_neutral'] }}</p>
                        </div>
                        <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/60">
                            <p class="text-xs uppercase text-rose-400">Bearish</p>
                            <p class="font-semibold mt-1">{{ $decision['scenarios']['bearish'] }}</p>
                            <p class="text-xs text-slate-400 mt-2">{{ $prediction['scenario_bearish'] }}</p>
                        </div>
                    </div>
                    <div class="mt-3 text-xs text-slate-400">Basis Prediksi: {{ $prediction['prediction_basis'] ?? 'Heuristik baseline' }} ({{ $prediction['method'] }})</div>
                </x-panel>

                <x-panel padding="p-6">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-semibold">Headline Penting</h3>
                        <a href="{{ route('news.index', ['code' => $stock->code]) }}" class="text-xs text-sky-400">Lihat semua</a>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div class="space-y-3">
                            <p class="text-xs uppercase text-green-400">Top Positive</p>
                            @forelse($topPositiveArticles as $article)
                                <div class="border border-slate-800 rounded-xl p-3 bg-slate-900/40">
                                    <div class="flex items-center justify-between gap-2">
                                        <p class="font-semibold text-sm">{{ \Illuminate\Support\Str::limit($article->title, 70) }}</p>
                                        <x-sentiment-badge :label="$article->sentiment_label ?? 'neutral'" />
                                    </div>
                                    <p class="text-[11px] text-slate-400">{{ $article->published_at?->format('d M Y') }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                    <p class="text-xs text-slate-400 mt-1">Skor {{ $article->sentiment_score ?? '-' }} • {{ $article->sentiment_method ?? 'rule_based' }}</p>
                                </div>
                            @empty
                                <p class="text-sm text-slate-400">Tidak ada headline positif.</p>
                            @endforelse
                        </div>
                        <div class="space-y-3">
                            <p class="text-xs uppercase text-rose-400">Top Risk</p>
                            @forelse($topRiskArticles as $article)
                                <div class="border border-slate-800 rounded-xl p-3 bg-slate-900/40">
                                    <div class="flex items-center justify-between gap-2">
                                        <p class="font-semibold text-sm">{{ \Illuminate\Support\Str::limit($article->title, 70) }}</p>
                                        <x-sentiment-badge :label="$article->sentiment_label ?? 'neutral'" />
                                    </div>
                                    <p class="text-[11px] text-slate-400">{{ $article->published_at?->format('d M Y') }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                    <p class="text-xs text-slate-400 mt-1">Skor {{ $article->sentiment_score ?? '-' }} • {{ $article->sentiment_method ?? 'rule_based' }}</p>
                                </div>
                            @empty
                                <p class="text-sm text-slate-400">Tidak ada headline risiko.</p>
                            @endforelse
                        </div>
                    </div>
                </x-panel>
            </div>

            <div class="col-span-12 xl:col-span-4 space-y-5">
                <x-panel padding="p-5">
                    <p class="text-xs uppercase text-slate-400">Insight Otomatis</p>
                    <div class="mt-2 space-y-2">
                        @foreach($decision['insights'] as $insight)
                            <div class="flex items-start gap-2">
                                <span class="mt-1 h-2 w-2 rounded-full bg-sky-400"></span>
                                <p class="text-sm">{{ $insight }}</p>
                            </div>
                        @endforeach
                        <div class="flex items-start gap-2 text-xs text-slate-400 mt-3">
                            <span class="mt-1 h-2 w-2 rounded-full bg-amber-400"></span>
                            <p>Prediksi bersifat indikatif, bukan rekomendasi investasi.</p>
                        </div>
                    </div>
                </x-panel>

                <x-panel padding="p-5">
                    <p class="text-xs uppercase text-slate-400">Lonjakan Berita</p>
                    <div class="space-y-2 mt-2">
                        @forelse($volumeImpact['peak_volume_dates'] ?? [] as $row)
                            <div class="flex items-center justify-between text-sm">
                                <div>
                                    <div class="font-semibold">{{ \Carbon\Carbon::parse($row['date'])->format('d M') }}</div>
                                    <div class="text-xs text-slate-400">Avg {{ $row['avg'] }} • {{ $row['count'] }} berita</div>
                                </div>
                                <span class="text-[11px] text-slate-400">Volume tinggi</span>
                            </div>
                        @empty
                            <p class="text-sm text-slate-400">Belum ada lonjakan volume.</p>
                        @endforelse
                    </div>
                </x-panel>

                <x-panel padding="p-5">
                    <p class="text-xs uppercase text-slate-400">Artikel Berpengaruh</p>
                    <div class="space-y-3 mt-2">
                        @forelse($articles as $article)
                            <div class="border border-slate-800 rounded-lg p-3 bg-slate-900/40">
                                <div class="flex items-start justify-between gap-2">
                                    <div>
                                        <p class="font-semibold text-sm">{{ \Illuminate\Support\Str::limit($article->title, 72) }}</p>
                                        <p class="text-[11px] text-slate-400">{{ $article->published_at?->format('d M H:i') }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                    </div>
                                    <x-sentiment-badge :label="$article->sentiment_label ?? 'neutral'" />
                                </div>
                                <div class="flex items-center justify-between text-[11px] text-slate-400 mt-2">
                                    <span>Skor {{ $article->sentiment_score ?? '-' }} | Conf {{ $article->sentiment_confidence ?? '-' }}</span>
                                    <span class="px-2 py-0.5 rounded-full border border-slate-700">{{ $article->sentiment_method ?? 'rule_based' }}</span>
                                </div>
                            </div>
                        @empty
                            <p class="text-sm text-slate-400">Belum ada artikel.</p>
                        @endforelse
                    </div>
                </x-panel>

                <x-panel padding="p-5">
                    <p class="text-xs uppercase text-slate-400">Top Dibahas</p>
                    <h3 class="font-semibold mb-3">Emiten Terhangat</h3>
                    <div class="space-y-2">
                        @foreach($topStocks as $row)
                            <div class="flex items-center justify-between px-3 py-2 rounded-lg border border-slate-800 hover:border-slate-700">
                                <div>
                                    <div class="font-semibold">{{ $row->stock?->code ?? '-' }}</div>
                                    <div class="text-xs text-slate-400">{{ $row->stock?->company_name ?? '' }}</div>
                                </div>
                                <span class="text-xs text-slate-300">{{ $row->total }} berita</span>
                            </div>
                        @endforeach
                    </div>
                </x-panel>
            </div>
        </div>
    </div>

    @push('scripts')
        <script>
            const priceSentimentCtx = document.getElementById('priceSentimentChart');
            const chartData = @json($chartData);
            const labels = chartData.labels || [];
            const rawDates = chartData.raw_dates || [];

            if (priceSentimentCtx && labels.length) {
                const dateIndex = new Map();
                rawDates.forEach((d, idx) => dateIndex.set(d, idx));

                const positiveEvents = [];
                const negativeEvents = [];
                (chartData.events?.positive_events || []).forEach(evt => {
                    const idx = dateIndex.get(evt.date);
                    if (idx !== undefined) {
                        positiveEvents.push({x: labels[idx], y: evt.sentiment, impact: evt.impact, type: 'positive'});
                    }
                });
                (chartData.events?.negative_events || []).forEach(evt => {
                    const idx = dateIndex.get(evt.date);
                    if (idx !== undefined) {
                        negativeEvents.push({x: labels[idx], y: evt.sentiment, impact: evt.impact, type: 'negative'});
                    }
                });

                new window.Chart(priceSentimentCtx, {
                    data: {
                        labels,
                        datasets: [
                            {
                                type: 'line',
                                label: 'Harga Penutupan',
                                data: chartData.prices,
                                borderColor: '#38bdf8',
                                backgroundColor: 'rgba(56,189,248,0.15)',
                                fill: true,
                                tension: 0.35,
                                yAxisID: 'y',
                            },
                            {
                                type: 'bar',
                                label: 'Skor Sentimen',
                                data: chartData.sentiments,
                                backgroundColor: 'rgba(34,197,94,0.35)',
                                borderColor: '#22c55e',
                                yAxisID: 'y1',
                            },
                            {
                                type: 'bar',
                                label: 'Volume Berita',
                                data: chartData.volume,
                                backgroundColor: 'rgba(148,163,184,0.25)',
                                borderColor: '#94a3b8',
                                yAxisID: 'y2',
                            },
                            {
                                type: 'scatter',
                                label: 'Event Sentimen +',
                                data: positiveEvents,
                                borderColor: '#22c55e',
                                backgroundColor: '#22c55e',
                                yAxisID: 'y1',
                                pointStyle: 'triangle',
                                pointRadius: 6,
                                showLine: false,
                            },
                            {
                                type: 'scatter',
                                label: 'Event Sentimen -',
                                data: negativeEvents,
                                borderColor: '#f43f5e',
                                backgroundColor: '#f43f5e',
                                yAxisID: 'y1',
                                pointStyle: 'triangle',
                                pointRadius: 6,
                                showLine: false,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            y: {
                                position: 'left',
                                grid: { color: '#1e293b' },
                                ticks: { color: '#cbd5e1' },
                            },
                            y1: {
                                position: 'right',
                                grid: { drawOnChartArea: false },
                                min: -1,
                                max: 1,
                                ticks: { color: '#cbd5e1' },
                            },
                            y2: {
                                position: 'right',
                                grid: { drawOnChartArea: false },
                                ticks: { color: '#cbd5e1' },
                                title: { display: true, text: 'Volume', color: '#cbd5e1' },
                            },
                            x: {
                                ticks: { color: '#cbd5e1' },
                                grid: { display: false },
                            },
                        },
                        plugins: {
                            legend: { labels: { color: '#cbd5e1' } },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                callbacks: {
                                    label: function(ctx) {
                                        if (ctx.dataset.type === 'scatter' && ctx.raw?.impact) {
                                            return `Event ${ctx.dataset.label.includes('+') ? 'positif' : 'negatif'}: Sent ${ctx.raw.y}, H+1 ${ctx.raw.impact.h1 ?? 'n/a'}%`;
                                        }
                                        return `${ctx.dataset.label}: ${ctx.formattedValue}`;
                                    }
                                }
                            },
                        },
                    },
                });
            }
        </script>
    @endpush
</x-app-layout>
