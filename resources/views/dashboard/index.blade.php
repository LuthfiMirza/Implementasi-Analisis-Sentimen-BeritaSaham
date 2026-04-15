<x-app-layout x-data="watchlistToggle()" x-init="init()">
    @php
        $pricePoints = $price_series->map(fn ($p) => [
            'date' => $p->price_date?->format('d M'),
            'close' => $p->close,
        ]);
    @endphp

    <div class="grid grid-cols-12 gap-6 relative">
        {{-- Floating handle to reopen sidebar --}}
        <div class="hidden lg:block fixed left-4 top-28 z-30" x-show="!open">
            <button type="button"
                    class="inline-flex items-center gap-2 px-3 py-2 text-xs rounded-lg border border-slate-800 bg-slate-900/80 hover:border-slate-600 transition shadow-lg shadow-slate-900/40"
                    x-on:click="open = true">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h10"/>
                </svg>
                Buka Watchlist
            </button>
        </div>

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
        <div class="col-span-12 lg:col-span-3 space-y-4" x-show="open" x-cloak>
            @include('dashboard.partials.sidebar', ['watchlist' => $watchlist, 'stocks' => $stocks, 'watchlistInsights' => $watchlist_insights ?? collect()])
        </div>

        {{-- Main Center --}}
        @php
            $initialQuote = [
                'stock_code' => $stock->code,
                'last' => isset($live_quote['last']) ? (float) $live_quote['last'] : ($latest_price?->close !== null ? (float) $latest_price->close : null),
                'open' => isset($live_quote['open']) ? (float) $live_quote['open'] : ($latest_price?->open !== null ? (float) $latest_price->open : null),
                'high' => isset($live_quote['high']) ? (float) $live_quote['high'] : ($latest_price?->high !== null ? (float) $latest_price->high : null),
                'low' => isset($live_quote['low']) ? (float) $live_quote['low'] : ($latest_price?->low !== null ? (float) $latest_price->low : null),
                'volume' => isset($live_quote['volume']) ? (int) $live_quote['volume'] : ($latest_price?->volume !== null ? (int) $latest_price->volume : null),
                'change_percent' => $live_quote['change_percent'] ?? $price_change_pct,
                'source' => $live_quote['source'] ?? 'snapshot',
                'is_live' => $live_quote['is_live'] ?? false,
                'fetched_at' => $live_quote['fetched_at'] ?? ($latest_price?->price_date?->toDateTimeString()),
            ];
        @endphp
        <div class="col-span-12 space-y-5 lg:space-y-6" :class="open ? 'lg:col-span-6' : 'lg:col-span-9'">
            <div x-data="priceQuote({{ json_encode($initialQuote) }}, {{ json_encode($price_change_pct) }})" x-init="startPolling('/api/stocks/{{ $stock->code }}/quote')">
            <x-panel padding="p-5" class="space-y-5">
                <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <div class="text-xs text-slate-400 uppercase">Saham Aktif</div>
                        <div class="flex items-center gap-3">
                            <h1 class="text-3xl font-bold tracking-tight">{{ $stock->code }}</h1>
                            <span class="text-slate-400">{{ $stock->company_name }}</span>
                        </div>
                        <div class="text-sm text-slate-400">{{ $stock->sector ?? 'Sektor tidak diketahui' }}</div>
                    </div>
                    <div class="text-right space-y-1">
                        <div class="flex items-center justify-end gap-2 flex-wrap">
                            <div class="text-3xl font-bold" x-text="formatNumber(quote.last)">{{ $initialQuote['last'] ? number_format($initialQuote['last'], 2) : '-' }}</div>
                            <span class="px-2 py-1 rounded-full text-[11px]" :class="quote.is_live ? 'bg-green-500/10 text-green-300 border border-green-500/30' : 'bg-slate-800 text-slate-200 border border-slate-700'">
                                <span x-text="quote.is_live ? 'Backend Live' : 'Backend Snapshot'"></span>
                            </span>
                            <span class="flex items-center gap-1 px-2 py-1 rounded-full text-[11px] border border-slate-700 bg-slate-800/60">
                                <span class="w-1.5 h-1.5 rounded-full animate-pulse" :class="marketStatus().dot"></span>
                                <span :class="marketStatus().color" x-text="marketStatus().label">BEI</span>
                            </span>
                            @if($chart_mode === 'tradingview')
                                <span class="px-2 py-1 rounded-full text-[11px] border border-sky-500/40 text-sky-200 bg-sky-500/10">
                                    Live Chart: TradingView
                                </span>
                            @endif
                        </div>
                        <div class="text-sm" :class="changePercent() >=0 ? 'text-green-400' : 'text-rose-400'" x-text="formatPercent(changePercent())">
                            {{ $price_change_pct ? number_format($price_change_pct, 2).'%' : '0.00%' }}
                        </div>
                        <div class="text-[11px] text-slate-500 leading-snug">
                            <span x-text="'Sumber kartu: ' + (quote.source ?? 'backend') + ' • ' + (quote.fetched_at ?? 'baru')"></span>
                        </div>
                        @if($chart_mode === 'tradingview')
                            <div class="text-[11px] text-sky-200/80 leading-snug">Harga acuan live: TradingView (chart di bawah).</div>
                        @endif
                    </div>
                </div>

                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 pt-1">
                    <div class="rounded-xl border-b border-l border-r border-slate-800 border-t-4 border-t-slate-500 bg-slate-900/70 p-3 min-h-[90px]">
                        <p class="text-[11px] uppercase text-slate-400">Open</p>
                        <p class="text-2xl font-bold text-slate-50" x-text="quote.open != null ? formatNumber(quote.open) : '—'">{{ $initialQuote['open'] ? number_format($initialQuote['open'], 2) : '—' }}</p>
                    </div>
                    <div class="rounded-xl border-b border-l border-r border-slate-800 border-t-4 border-t-green-500 bg-slate-900/70 p-3 min-h-[90px]">
                        <p class="text-[11px] uppercase text-slate-400">High</p>
                        <p class="text-2xl font-bold" :class="quote.high != null ? 'text-green-400' : 'text-slate-500'" x-text="quote.high != null ? formatNumber(quote.high) : '—'">{{ $initialQuote['high'] ? number_format($initialQuote['high'], 2) : '—' }}</p>
                    </div>
                    <div class="rounded-xl border-b border-l border-r border-slate-800 border-t-4 border-t-rose-500 bg-slate-900/70 p-3 min-h-[90px]">
                        <p class="text-[11px] uppercase text-slate-400">Low</p>
                        <p class="text-2xl font-bold" :class="quote.low != null ? 'text-rose-400' : 'text-slate-500'" x-text="quote.low != null ? formatNumber(quote.low) : '—'">{{ $initialQuote['low'] ? number_format($initialQuote['low'], 2) : '—' }}</p>
                    </div>
                    <div class="rounded-xl border-b border-l border-r border-slate-800 border-t-4 border-t-sky-500 bg-slate-900/70 p-3 min-h-[90px]">
                        <p class="text-[11px] uppercase text-slate-400">Volume</p>
                        <p class="text-2xl font-bold text-slate-50" x-text="quote.volume != null ? formatVolume(quote.volume) : '—'">{{ $initialQuote['volume'] ? number_format($initialQuote['volume']) : '—' }}</p>
                    </div>
                </div>
                <div class="text-[11px] text-slate-500 mt-2 leading-snug">
                    <span x-text="quote.is_live ? 'Kartu: backend live • Chart live: TradingView.' : 'Kartu: snapshot backend terakhir • Acuan live: TradingView (chart di bawah).'"></span>
                </div>
            </x-panel>

            <x-panel padding="p-5" class="mt-5 lg:mt-6">
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

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 lg:mt-5">
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
        </div>

        {{-- Right Column --}}
        <div class="col-span-12 lg:col-span-3 flex flex-col gap-4">
            <x-panel class="flex-none">
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

            <x-panel class="flex-1 flex flex-col min-h-[360px]" x-data="newsRefresh('{{ $stock->code }}')">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <h3 class="font-semibold">Berita Terkini</h3>
                        <p class="text-[11px] text-slate-500 mt-0.5" x-text="lastRefreshed">
                            {{ now()->format('d M H:i') }}
                        </p>
                    </div>
                    <div class="flex items-center gap-2">
                        <a href="{{ route('news.index', ['code' => $stock->code]) }}" class="text-xs text-sky-400 hover:underline">Lihat semua</a>
                        <button @click="refresh()"
                                :disabled="loading"
                                class="flex items-center gap-1 px-2 py-1 rounded-lg border border-slate-700
                                       bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 transition
                                       disabled:opacity-50 disabled:cursor-wait">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" :class="loading ? 'animate-spin' : ''"
                                 fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                            </svg>
                            <span x-text="loading ? 'Fetching...' : 'Refresh'">Refresh</span>
                        </button>
                    </div>
                </div>

                <div x-show="savedCount !== null" x-cloak
                     class="mb-2 px-2 py-1 rounded-lg bg-green-500/10 border border-green-500/20 text-[11px] text-green-400"
                     x-text="savedCount + ' artikel baru disimpan'">
                </div>

                <div x-show="error" x-cloak
                     class="mb-2 px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/20 text-[11px] text-rose-400"
                     x-text="error">
                </div>

                <div class="flex gap-3 mb-3 text-[11px]">
                    <span class="text-green-400">▲ {{ $news->where('sentiment_label','positive')->count() }} positif</span>
                    <span class="text-slate-400">◆ {{ $news->where('sentiment_label','neutral')->count() }} netral</span>
                    <span class="text-rose-400">▼ {{ $news->where('sentiment_label','negative')->count() }} negatif</span>
                </div>

                <div class="overflow-hidden rounded-xl border border-slate-800/80 flex-1">
                        <div class="max-h-[520px] overflow-y-auto divide-y divide-slate-800" id="newsContainer">
                        {{-- Server-rendered cards: always visible on load until refresh --}}
                        <div id="serverArticles">
                            @forelse($news as $article)
                                @php
                                    $sent = $article->sentiment_label ?? 'neutral';
                                    $sentLabel = $sent === 'positive' ? '🟢 Positif' : ($sent === 'negative' ? '🔴 Negatif' : '⚪ Netral');
                                    $sentClass = $sent === 'positive' ? 'bg-green-500/20 text-green-400' : ($sent === 'negative' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20 text-gray-400');
                                    $sourceLabel = match($article->source_provider) {
                                        'rss_local' => 'CNBC ID',
                                        'gnews' => 'GNews',
                                        'gdelt' => 'GDELT',
                                        default => $article->source_provider ?? 'RSS',
                                    };
                                    $stars = match($article->relevance_band) {
                                        'high' => '★★★',
                                        'medium' => '★★',
                                        default => '★',
                                    };
                                    $diffHours = now()->diffInHours($article->published_at);
                                    $timeAgo = $diffHours < 1 ? 'baru saja'
                                      : ($diffHours < 24 ? $diffHours.' jam lalu'
                                      : now()->diffInDays($article->published_at).' hari lalu');
                                @endphp
                                <a href="{{ $article->source_url ?? '#' }}" target="_blank" rel="noopener"
                                   class="block p-3 hover:bg-white/5 transition border-b border-slate-800 group border-l-2 ml-0
                                   {{ ($article->sentiment_label === 'positive') ? 'border-l-green-500' : (($article->sentiment_label === 'negative') ? 'border-l-rose-500' : 'border-l-slate-700') }}">
                                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                                        <span class="text-xs px-1.5 py-0.5 rounded font-medium {{ $sentClass }}">
                                            {{ $sentLabel }}
                                        </span>
                                        <span class="text-xs text-gray-500">{{ $sourceLabel }}</span>
                                        <span class="text-xs text-yellow-600/70">{{ $stars }}</span>
                                        <span class="text-xs text-gray-600 ml-auto">{{ $timeAgo }}</span>
                                    </div>
                                    <p class="text-sm text-gray-200 group-hover:text-white transition line-clamp-2 leading-snug">
                                        {{ $article->title }}
                                    </p>
                                </a>
                            @empty
                                <div class="px-3 py-6 text-center text-sm text-slate-400">
                                    Belum ada berita. Klik Refresh untuk fetch terbaru.
                                </div>
                            @endforelse
                        </div>

                        {{-- Alpine-rendered cards: shown AFTER refresh --}}
                        <div id="alpineArticles" style="display:none">
                            <template x-if="articles.length > 0">
                                <template x-for="article in articles" :key="article.url">
                                    <a :href="article.url || '#'" target="_blank"
                                       class="block p-3 hover:bg-white/5 transition border-b border-slate-800 border-l-2 ml-0"
                                       :class="article.sentiment === 'positive' ? 'border-l-green-500' : (article.sentiment === 'negative' ? 'border-l-rose-500' : 'border-l-slate-700')">
                                        <div class="flex items-center gap-2 mb-1 flex-wrap">
                                            <span class="text-xs px-1.5 py-0.5 rounded font-medium"
                                                  :class="{
                                                    'bg-green-500/20 text-green-400': article.sentiment === 'positive',
                                                    'bg-red-500/20 text-red-400': article.sentiment === 'negative',
                                                    'bg-gray-500/20 text-gray-400': article.sentiment !== 'positive' && article.sentiment !== 'negative'
                                                  }"
                                                  x-text="article.sentiment === 'positive' ? '🟢 Positif' : (article.sentiment === 'negative' ? '🔴 Negatif' : '⚪ Netral')">
                                            </span>
                                            <span class="text-xs text-gray-500" x-text="article.source || 'RSS'"></span>
                                            <span class="text-xs text-yellow-600/70"
                                                  x-text="article.quality === 'high' ? '★★★' : (article.quality === 'medium' ? '★★' : '★')">
                                            </span>
                                            <span class="text-xs text-gray-600 ml-auto" x-text="article.relative || article.published"></span>
                                        </div>
                                        <p class="text-sm text-gray-200 line-clamp-2 leading-snug" x-text="article.title"></p>
                                    </a>
                                </template>
                            </template>
                            <template x-if="articles.length === 0">
                                <div class="px-3 py-6 text-center text-sm text-slate-400">
                                    Tidak ada artikel baru ditemukan.
                                </div>
                            </template>
                        </div>
                    </div>
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

@push('scripts')
<script>
function newsRefresh(stockCode) {
    return {
        loading: false,
        refreshed: false,
        articles: [],
        savedCount: null,
        error: null,
        lastRefreshed: 'Terakhir: baru saja',

        async refresh() {
            this.loading = true;
            this.error = null;
            this.savedCount = null;

            try {
                const res = await fetch(`/api/news/refresh/${stockCode}`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    },
                });

                if (!res.ok) throw new Error('Gagal fetch berita');

                const data = await res.json();
                this.articles = data.articles || [];
                this.savedCount = data.saved;
                this.refreshed = true;
                // Swap: hide server cards, show Alpine cards
                const srv = document.getElementById('serverArticles');
                const alp = document.getElementById('alpineArticles');
                if (srv) srv.style.display = 'none';
                if (alp) alp.style.display = 'block';

                const now = new Date();
                this.lastRefreshed = 'Diperbarui: ' +
                    now.toLocaleDateString('id-ID', {day:'2-digit', month:'short'}) +
                    ' ' + now.toLocaleTimeString('id-ID', {hour:'2-digit', minute:'2-digit'});

                setTimeout(() => { this.savedCount = null; }, 5000);
            } catch (e) {
                this.error = e.message || 'Terjadi kesalahan saat refresh berita';
            } finally {
                this.loading = false;
            }
        }
    }
}
</script>
@endpush
