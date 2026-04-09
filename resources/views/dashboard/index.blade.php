<x-app-layout>
    @php
        $pricePoints = $price_series->map(fn ($p) => [
            'date' => $p->price_date?->format('d M'),
            'close' => $p->close,
        ]);
    @endphp

    <div class="grid grid-cols-12 gap-6">
        @if(($watchlist_alerts ?? collect())->isNotEmpty())
            <div class="col-span-12">
                <div class="rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm text-rose-100">
                    <div class="font-semibold mb-1">Alert Watchlist</div>
                    <div class="space-y-1">
                        @foreach($watchlist_alerts as $alert)
                            <div>• {{ $alert['stock']->code }}: {{ $alert['negative_alert_count'] }} berita negatif dalam 24 jam terakhir.</div>
                        @endforeach
                    </div>
                </div>
            </div>
        @endif
        {{-- Sidebar Watchlist --}}
        <div class="col-span-12 lg:col-span-3 space-y-4">
            @include('dashboard.partials.sidebar', ['watchlist' => $watchlist, 'stocks' => $stocks, 'watchlistInsights' => $watchlist_insights ?? collect()])
        </div>

        {{-- Main Center --}}
        <div class="col-span-12 lg:col-span-6 space-y-5">
            <x-panel padding="p-5">
                <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <div class="text-xs text-slate-400 uppercase">Saham Aktif</div>
                        <div class="flex items-center gap-3">
                            <h1 class="text-3xl font-bold tracking-tight">{{ $stock->code }}</h1>
                            <span class="text-slate-400">{{ $stock->company_name }}</span>
                        </div>
                        <div class="text-sm text-slate-400">{{ $stock->sector ?? 'Sektor tidak diketahui' }}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-3xl font-bold">{{ $latest_price?->close ? number_format($latest_price->close, 2) : '-' }}</div>
                        <div class="text-sm {{ ($price_change_pct ?? 0) >=0 ? 'text-green-400' : 'text-rose-400' }}">
                            {{ $price_change_pct ? number_format($price_change_pct, 2) : '0.00' }}%
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                    <x-metric-card label="Open" :value="$latest_price?->open ? number_format($latest_price->open, 2) : '-'" />
                    <x-metric-card label="High" :value="$latest_price?->high ? number_format($latest_price->high, 2) : '-'" />
                    <x-metric-card label="Low" :value="$latest_price?->low ? number_format($latest_price->low, 2) : '-'" />
                    <x-metric-card label="Volume" :value="$latest_price?->volume ? number_format($latest_price->volume) : '-'" />
                </div>
            </x-panel>

            <x-panel padding="p-5">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <p class="text-xs text-slate-400 uppercase">Harga</p>
                        <h3 class="font-semibold">Tren Harga</h3>
                    </div>
                    <x-timeframe-tabs :active="$interval" :code="$stock->code" routeName="dashboard" />
                </div>

                @if($chart_mode === 'internal')
                    <canvas id="priceChart" class="h-72"></canvas>
                @else
                    @php
                        $tvInterval = match($interval) {
                            '1w' => 'W',
                            '1m', '3m' => 'M',
                            default => 'D',
                        };
                    @endphp
                    <div class="h-80 rounded-xl border border-slate-800 overflow-hidden">
                        <iframe src="https://s.tradingview.com/widgetembed/?symbol={{ urlencode($stock->tradingview_symbol ?? (config('dashboard.tradingview_exchange').':'.$stock->code)) }}&interval={{ $tvInterval }}&symboledit=1&saveimage=0&toolbarbg=0f172a&studies=[]&theme=dark"
                                class="w-full h-full" allowtransparency="true" frameborder="0"></iframe>
                    </div>
                @endif
            </x-panel>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <x-metric-card label="Sentimen Positif" :value="$sentiment_summary['positive_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['positive']" />
                <x-metric-card label="Sentimen Netral" :value="$sentiment_summary['neutral_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['neutral']" />
                <x-metric-card label="Sentimen Negatif" :value="$sentiment_summary['negative_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['negative']" />
            </div>

            <x-panel padding="p-5">
                <div class="flex items-center justify-between mb-2">
                    <div>
                        <p class="text-xs text-slate-400 uppercase">Insight Otomatis</p>
                        <h3 class="font-semibold">Narasi Singkat</h3>
                    </div>
                    <a href="{{ route('analytics.index', ['code' => $stock->code]) }}" class="text-xs text-sky-400">Lihat analytics</a>
                </div>
                <p class="text-slate-200 leading-relaxed">{{ $insight }}</p>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                    @if($sentiment_summary['top_positive'])
                        <x-panel padding="p-3">
                            <p class="metric-label">Headline Positif</p>
                            <p class="text-sm font-semibold">{{ Str::limit($sentiment_summary['top_positive']->title, 80) }}</p>
                        </x-panel>
                    @endif
                    @if($sentiment_summary['top_negative'])
                        <x-panel padding="p-3">
                            <p class="metric-label">Headline Negatif</p>
                            <p class="text-sm font-semibold">{{ Str::limit($sentiment_summary['top_negative']->title, 80) }}</p>
                        </x-panel>
                    @endif
                </div>
            </x-panel>
        </div>

        {{-- Right Column --}}
        <div class="col-span-12 lg:col-span-3 space-y-4">
            <x-panel>
                <div class="flex items-center justify-between mb-2">
                    <div>
                        <p class="text-xs text-slate-400 uppercase">Sentimen</p>
                        <h3 class="font-semibold">Distribusi</h3>
                    </div>
                </div>
                <div class="space-y-3">
                    @foreach(['positive' => 'Positif', 'neutral' => 'Netral', 'negative' => 'Negatif'] as $key => $label)
                        <div>
                            <div class="flex justify-between text-xs text-slate-400">
                                <span>{{ $label }}</span>
                                <span>{{ $sentiment_summary[$key.'_pct'] }}%</span>
                            </div>
                            <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                                <div class="h-full {{ $key === 'positive' ? 'bg-green-500/80' : ($key === 'negative' ? 'bg-rose-500/80' : 'bg-amber-400/70') }}"
                                     style="width: {{ $sentiment_summary[$key.'_pct'] }}%"></div>
                            </div>
                        </div>
                    @endforeach
                </div>
            </x-panel>

            <x-panel>
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold">Berita Terkini</h3>
                    <a href="{{ route('news.index', ['code' => $stock->code]) }}" class="text-xs text-sky-400">Lihat semua</a>
                </div>
                <div class="overflow-hidden rounded-xl border border-slate-800/80">
                    <table class="w-full text-sm">
                        <tbody class="divide-y divide-slate-800">
                            @forelse($news as $article)
                                <tr class="hover:bg-slate-900/60">
                                    <td class="px-3 py-3">
                                        <div class="flex items-center justify-between gap-2">
                                            <div>
                                                <p class="font-semibold text-[13px] leading-tight">{{ Str::limit($article->title, 72) }}</p>
                                                <p class="text-[11px] text-slate-400">{{ $article->published_at?->format('d M H:i') }} • {{ $article->source?->name ?? 'Sumber' }}</p>
                                            </div>
                                            <x-sentiment-badge :label="$article->sentiment_label ?? 'neutral'" />
                                        </div>
                                    </td>
                                </tr>
                            @empty
                                <tr><td class="px-3 py-3 text-sm text-slate-400">Belum ada berita.</td></tr>
                            @endforelse
                        </tbody>
                    </table>
                </div>
            </x-panel>
        </div>
    </div>

    @if($chart_mode === 'internal')
        @push('scripts')
            <script>
                const priceSeries = @json($pricePoints);
                const ctx = document.getElementById('priceChart');
                if (ctx && priceSeries.length) {
                    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 280);
                    gradient.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
                    gradient.addColorStop(1, 'rgba(15, 23, 42, 0)');

                    new window.Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: priceSeries.map(p => p.date),
                            datasets: [{
                                label: 'Close',
                                data: priceSeries.map(p => p.close),
                                borderColor: '#38bdf8',
                                borderWidth: 2,
                                fill: true,
                                backgroundColor: gradient,
                                tension: 0.4,
                                pointRadius: 0,
                            }],
                        },
                        options: {
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                                y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                            },
                        },
                    });
                }
            </script>
        @endpush
    @endif
</x-app-layout>
