<x-app-layout x-data="watchlistToggle()" x-init="init()">
    @php
        $pricePoints = $price_series->map(fn ($p) => [
            'date' => $p->price_date?->format('d M'),
            'close' => $p->close,
        ]);
    @endphp

    <div class="dashboard-grid grid grid-cols-12 relative">
        {{-- Floating handle to reopen sidebar --}}
        <div class="hidden lg:block fixed left-4 top-28 z-30" x-show="!open">
            <button type="button"
                    class="dashboard-toggle-btn inline-flex items-center gap-2 px-3 py-2"
                    x-on:click="open = true">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h10"/>
                </svg>
                Buka Watchlist
            </button>
        </div>

        @if(($watchlist_alerts ?? collect())->isNotEmpty())
            <div class="col-span-12">
                <div class="dashboard-alert px-4 py-3 text-sm">
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
        <div class="dashboard-watchlist-column col-span-12 lg:col-span-3 space-y-4" x-show="open" x-cloak>
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
        <div class="dashboard-main-column col-span-12 space-y-5 lg:space-y-6" :class="open ? 'lg:col-span-6' : 'lg:col-span-9'">
            <div x-data="priceQuote({{ json_encode($initialQuote) }}, {{ json_encode($price_change_pct) }})" x-init="startPolling('/api/stocks/{{ $stock->code }}/quote')">
            <x-panel padding="p-5" class="panel-frame panel-frame-lg space-y-5">
                <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <div class="section-label">Saham Aktif</div>
                        <div class="flex items-center gap-3">
                            <h1 class="stock-symbol-badge">{{ $stock->code }}</h1>
                            <span class="stock-company-name">{{ $stock->company_name }}</span>
                        </div>
                        <div class="stock-sector">{{ $stock->sector ?? 'Sektor tidak diketahui' }}</div>
                    </div>
                    <div class="text-right space-y-1">
                        <div class="flex items-center justify-end gap-2 flex-wrap">
                            <div class="price-display" x-text="formatNumber(quote.last)">{{ $initialQuote['last'] ? number_format($initialQuote['last'], 2) : '-' }}</div>
                            <span class="status-badge" :class="quote.is_live ? 'status-badge-live' : 'status-badge-closed'">
                                <span x-text="quote.is_live ? 'Backend Live' : 'Backend Snapshot'"></span>
                            </span>
                            <span class="market-state-badge">
                                <span class="market-status-dot animate-pulse" :class="marketStatus().dot"></span>
                                <span :class="marketStatus().color" x-text="marketStatus().label">BEI</span>
                            </span>
                            @if($chart_mode === 'tradingview')
                                <span class="status-badge status-badge-info">
                                    Live Chart: TradingView
                                </span>
                            @endif
                        </div>
                        <div class="price-change" :class="changePercent() >=0 ? 'text-green-400' : 'text-rose-400'" x-text="formatPercent(changePercent())">
                            {{ $price_change_pct ? number_format($price_change_pct, 2).'%' : '0.00%' }}
                        </div>
                        <div class="quote-caption leading-snug">
                            <span x-text="'Sumber kartu: ' + (quote.source ?? 'backend') + ' • ' + (quote.fetched_at ?? 'baru')"></span>
                        </div>
                        @if($chart_mode === 'tradingview')
                            <div class="quote-source-note leading-snug">Harga acuan live: TradingView (chart di bawah).</div>
                        @endif
                    </div>
                </div>

                <div class="ohlcv-grid mt-6">
                    <div class="ohlcv-cell">
                        <p class="ohlcv-label">Open</p>
                        <p class="ohlcv-value" x-text="quote.open != null ? formatNumber(quote.open) : '—'">{{ $initialQuote['open'] ? number_format($initialQuote['open'], 2) : '—' }}</p>
                    </div>
                    <div class="ohlcv-cell">
                        <p class="ohlcv-label">High</p>
                        <p class="ohlcv-value" :class="quote.high != null ? 'text-green-400' : 'text-slate-500'" x-text="quote.high != null ? formatNumber(quote.high) : '—'">{{ $initialQuote['high'] ? number_format($initialQuote['high'], 2) : '—' }}</p>
                    </div>
                    <div class="ohlcv-cell">
                        <p class="ohlcv-label">Low</p>
                        <p class="ohlcv-value" :class="quote.low != null ? 'text-rose-400' : 'text-slate-500'" x-text="quote.low != null ? formatNumber(quote.low) : '—'">{{ $initialQuote['low'] ? number_format($initialQuote['low'], 2) : '—' }}</p>
                    </div>
                    <div class="ohlcv-cell">
                        <p class="ohlcv-label">Volume</p>
                        <p class="ohlcv-value" x-text="quote.volume != null ? formatVolume(quote.volume) : '—'">{{ $initialQuote['volume'] ? number_format($initialQuote['volume']) : '—' }}</p>
                    </div>
                </div>
                <div class="quote-source-note mt-2 leading-snug">
                    <span x-text="quote.is_live ? 'Kartu: backend live • Chart live: TradingView.' : 'Kartu: snapshot backend terakhir • Acuan live: TradingView (chart di bawah).'"></span>
                </div>
            </x-panel>

            <x-panel padding="p-5" class="panel-frame panel-frame-lg mt-5 lg:mt-6">
                <div class="panel-header">
                    <div>
                        <p class="panel-title">Harga</p>
                        <h3 class="panel-heading">Tren Harga</h3>
                    </div>
                    <x-timeframe-tabs class="timeframe-tabs" :active="$interval" :code="$stock->code" routeName="dashboard" />
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
                    <div class="chart-frame h-80">
                        <iframe src="https://s.tradingview.com/widgetembed/?symbol={{ urlencode($stock->tradingview_symbol ?? (config('dashboard.tradingview_exchange').':'.$stock->code)) }}&interval={{ $tvInterval }}&symboledit=1&saveimage=0&toolbarbg=0a0c10&studies=[]&theme=dark"
                                class="w-full h-full rounded-[10px]" allowtransparency="true" frameborder="0"></iframe>
                    </div>
                @endif
            </x-panel>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 lg:mt-5">
                <x-metric-card class="metric-panel" label="Sentimen Positif" :value="$sentiment_summary['positive_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['positive']" />
                <x-metric-card class="metric-panel" label="Sentimen Netral" :value="$sentiment_summary['neutral_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['neutral']" />
                <x-metric-card class="metric-panel" label="Sentimen Negatif" :value="$sentiment_summary['negative_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['negative']" />
            </div>

            <x-panel padding="p-5" class="panel-frame panel-frame-lg">
                <div class="panel-header">
                    <div>
                        <p class="panel-title">Insight Otomatis</p>
                        <h3 class="panel-heading">Narasi Singkat</h3>
                    </div>
                    <a href="{{ route('analytics.index', ['code' => $stock->code]) }}" class="panel-action-link">Lihat analytics</a>
                </div>
                <p class="panel-body-copy">{{ $insight }}</p>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                    @if($sentiment_summary['top_positive'])
                        <x-panel padding="p-3" class="panel-frame">
                            <p class="metric-label">Headline Positif</p>
                            <p class="headline-card-title">{{ Str::limit($sentiment_summary['top_positive']->title, 80) }}</p>
                        </x-panel>
                    @endif
                    @if($sentiment_summary['top_negative'])
                        <x-panel padding="p-3" class="panel-frame">
                            <p class="metric-label">Headline Negatif</p>
                            <p class="headline-card-title">{{ Str::limit($sentiment_summary['top_negative']->title, 80) }}</p>
                        </x-panel>
                    @endif
                </div>
            </x-panel>
            </div>
        </div>

        {{-- Right Column --}}
        <div class="dashboard-right-column col-span-12 lg:col-span-3 flex flex-col gap-4">
            <x-panel class="panel-frame flex-none">
                <div class="panel-header">
                    <div>
                        <p class="panel-title">Sentimen</p>
                        <h3 class="panel-heading">Distribusi</h3>
                    </div>
                </div>
                <div class="space-y-3">
                    @foreach(['positive' => 'Positif', 'neutral' => 'Netral', 'negative' => 'Negatif'] as $key => $label)
                        <div class="sentiment-row">
                            <div class="sentiment-row-head">
                                <span class="sentiment-label {{ $key === 'positive' ? 'sentiment-label-positive' : ($key === 'negative' ? 'sentiment-label-negative' : 'sentiment-label-neutral') }}">{{ $label }}</span>
                                <span class="sentiment-percent">{{ $sentiment_summary[$key.'_pct'] }}%</span>
                            </div>
                            <div class="sentiment-bar-track">
                                <div class="sentiment-bar-fill {{ $key === 'positive' ? 'sentiment-positive' : ($key === 'negative' ? 'sentiment-negative' : 'sentiment-neutral') }}"
                                     style="width: {{ $sentiment_summary[$key.'_pct'] }}%"></div>
                            </div>
                        </div>
                    @endforeach
                </div>
            </x-panel>

            <x-panel class="panel-frame flex-1 flex flex-col min-h-[360px]" x-data="newsRefresh('{{ $stock->code }}')">
                <div class="panel-header">
                    <div>
                        <h3 class="panel-heading">Berita Terkini</h3>
                        <p class="panel-meta mt-0.5" x-text="lastRefreshed">
                            {{ now()->format('d M H:i') }}
                        </p>
                    </div>
                    <div class="flex items-center gap-2">
                        <a href="{{ route('news.index', ['code' => $stock->code]) }}" class="panel-action-link">Lihat semua</a>
                        <button @click="refresh()"
                                :disabled="loading"
                                class="panel-action-button disabled:cursor-wait">
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
                     class="status-message status-message-success mb-2"
                     x-text="savedCount + ' artikel baru disimpan'">
                </div>

                <div x-show="error" x-cloak
                     class="status-message status-message-error mb-2"
                     x-text="error">
                </div>

                <div class="news-counts mb-3">
                    <span class="news-count text-green-400">▲ {{ $news->where('sentiment_label','positive')->count() }} positif</span>
                    <span class="news-count text-amber-400">◆ {{ $news->where('sentiment_label','neutral')->count() }} netral</span>
                    <span class="news-count text-rose-400">▼ {{ $news->where('sentiment_label','negative')->count() }} negatif</span>
                </div>

                <div class="news-list-shell overflow-hidden flex-1">
                        <div class="max-h-[520px] overflow-y-auto" id="newsContainer">
                        {{-- Server-rendered cards: always visible on load until refresh --}}
                        <div id="serverArticles">
                            @forelse($news as $article)
                                @php
                                    $sent = $article->sentiment_label ?? 'neutral';
                                    $sentLabel = $sent === 'positive' ? 'Positif' : ($sent === 'negative' ? 'Negatif' : 'Netral');
                                    $sentClass = $sent === 'positive' ? 'news-chip news-chip-positive' : ($sent === 'negative' ? 'news-chip news-chip-negative' : 'news-chip news-chip-neutral');
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
                                   class="news-item group border-b border-white/10 {{ ($article->sentiment_label === 'positive') ? 'news-item-positive' : (($article->sentiment_label === 'negative') ? 'news-item-negative' : 'news-item-neutral') }}">
                                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                                        <span class="{{ $sentClass }}">
                                            {{ $sentLabel }}
                                        </span>
                                        <span class="news-source">{{ $sourceLabel }}</span>
                                        <span class="news-quality">{{ $stars }}</span>
                                        <span class="news-timestamp ml-auto">{{ $timeAgo }}</span>
                                    </div>
                                    <p class="news-title">
                                        {{ $article->title }}
                                    </p>
                                </a>
                            @empty
                                <div class="news-empty-state">
                                    Belum ada berita. Klik Refresh untuk fetch terbaru.
                                </div>
                            @endforelse
                        </div>

                        {{-- Alpine-rendered cards: shown AFTER refresh --}}
                        <div id="alpineArticles" style="display:none">
                            <template x-if="articles.length > 0">
                                <template x-for="article in articles" :key="article.url">
                                    <a :href="article.url || '#'" target="_blank"
                                       class="news-item border-b border-white/10"
                                       :class="article.sentiment === 'positive' ? 'news-item-positive' : (article.sentiment === 'negative' ? 'news-item-negative' : 'news-item-neutral')">
                                        <div class="flex items-center gap-2 mb-1 flex-wrap">
                                            <span
                                                  :class="{
                                                    'news-chip news-chip-positive': article.sentiment === 'positive',
                                                    'news-chip news-chip-negative': article.sentiment === 'negative',
                                                    'news-chip news-chip-neutral': article.sentiment !== 'positive' && article.sentiment !== 'negative'
                                                  }"
                                                  x-text="article.sentiment === 'positive' ? 'Positif' : (article.sentiment === 'negative' ? 'Negatif' : 'Netral')">
                                            </span>
                                            <span class="news-source" x-text="article.source || 'RSS'"></span>
                                            <span class="news-quality"
                                                  x-text="article.quality === 'high' ? '★★★' : (article.quality === 'medium' ? '★★' : '★')">
                                            </span>
                                            <span class="news-timestamp ml-auto" x-text="article.relative || article.published"></span>
                                        </div>
                                        <p class="news-title" x-text="article.title"></p>
                                    </a>
                                </template>
                            </template>
                            <template x-if="articles.length === 0">
                                <div class="news-empty-state">
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
