<x-app-layout>
    @php
        $pricePoints = $price_series->map(fn ($p) => [
            'date' => $p->price_date?->format('d M'),
            'close' => $p->close,
        ]);

        $sentimentBreakdown = [
            ['key' => 'positive', 'label' => 'Positif', 'count' => $sentiment_summary['positive'], 'pct' => (float) $sentiment_summary['positive_pct'], 'color' => '#22c55e'],
            ['key' => 'neutral', 'label' => 'Netral', 'count' => $sentiment_summary['neutral'], 'pct' => (float) $sentiment_summary['neutral_pct'], 'color' => '#f59e0b'],
            ['key' => 'negative', 'label' => 'Negatif', 'count' => $sentiment_summary['negative'], 'pct' => (float) $sentiment_summary['negative_pct'], 'color' => '#ef4444'],
        ];

        $totalAnalyzed = collect($sentimentBreakdown)->sum('count');
        $circumference = 2 * pi() * 36;
        $offset = 0;
        $donutSegments = collect($sentimentBreakdown)->map(function ($item) use (&$offset, $circumference) {
            $length = $item['pct'] <= 0 ? 0 : ($item['pct'] / 100) * $circumference;
            $segment = $item + [
                'length' => $length,
                'offset' => $offset,
            ];
            $offset += $length;

            return $segment;
        });
    @endphp

    <div x-data="dashboardPage()" class="dashboard-page space-y-4">
        @if(($watchlist_alerts ?? collect())->isNotEmpty())
            <div class="dashboard-alert px-4 py-3 text-sm">
                <div class="font-semibold mb-1">Alert Watchlist</div>
                <div class="space-y-1">
                    @foreach($watchlist_alerts as $alert)
                        <div>• {{ $alert['stock']->code }}: {{ $alert['negative_alert_count'] }} berita negatif dalam 24 jam terakhir.</div>
                    @endforeach
                </div>
            </div>
        @endif

        <div class="dashboard-workspace">
            <div class="dashboard-watchlist-shell">
                @include('dashboard.partials.sidebar', ['watchlist' => $watchlist, 'stocks' => $stocks, 'watchlistInsights' => $watchlist_insights ?? collect()])
            </div>

            <div class="dashboard-content-row">
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

                <div class="dashboard-main-column">
                    <div x-data="priceQuote({{ json_encode($initialQuote) }}, {{ json_encode($price_change_pct) }})" x-init="startPolling('/api/stocks/{{ $stock->code }}/quote')" class="space-y-4">
                        <x-panel padding="p-5" class="panel-frame panel-frame-lg space-y-5">
                            <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                <div>
                                    <div class="section-label">Saham Aktif</div>
                                    <div class="flex items-center gap-3 flex-wrap">
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
                                    <div class="price-change" :class="changePercent() >= 0 ? 'text-green-400' : 'text-rose-400'" x-text="formatPercent(changePercent())">
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

                            <div class="ohlcv-grid">
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
                            <div class="quote-source-note leading-snug">
                                <span x-text="quote.is_live ? 'Kartu: backend live • Chart live: TradingView.' : 'Kartu: snapshot backend terakhir • Acuan live: TradingView (chart di bawah).'"></span>
                            </div>
                        </x-panel>

                        <x-panel padding="p-5" class="panel-frame panel-frame-lg">
                            <div class="panel-header panel-header-chart">
                                <div>
                                    <p class="panel-title">Harga</p>
                                    <h3 class="panel-heading">Tren Harga</h3>
                                </div>
                                <div class="chart-toolbar">
                                    <x-timeframe-tabs class="timeframe-tabs" :active="$interval" :code="$stock->code" routeName="dashboard" />
                                    <button type="button"
                                            class="panel-action-button panel-action-button-compact hidden lg:inline-flex"
                                            @click="toggleRightPanel()"
                                            :aria-pressed="rightPanelOpen">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 transition-transform duration-200" :class="rightPanelOpen ? '' : 'rotate-180'" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                                        </svg>
                                        <span x-text="rightPanelOpen ? 'Sembunyikan Panel' : 'Tampilkan Panel'">Sembunyikan Panel</span>
                                    </button>
                                </div>
                            </div>

                            @if($chart_mode === 'internal')
                                <canvas id="priceChart" class="chart-canvas"></canvas>
                            @else
                                @php
                                    $tvInterval = match($interval) {
                                        '1w' => 'W',
                                        '1m', '3m' => 'M',
                                        default => 'D',
                                    };
                                @endphp
                                <div class="chart-frame chart-frame-live">
                                    <iframe src="https://s.tradingview.com/widgetembed/?symbol={{ urlencode($stock->tradingview_symbol ?? (config('dashboard.tradingview_exchange').':'.$stock->code)) }}&interval={{ $tvInterval }}&symboledit=1&saveimage=0&toolbarbg=0a0c10&studies=[]&theme=dark"
                                            class="w-full h-full rounded-[10px]" allowtransparency="true" frameborder="0"></iframe>
                                </div>
                            @endif
                        </x-panel>

                        <div class="dashboard-metrics-grid">
                            <x-metric-card class="metric-panel" label="Sentimen Positif" :value="$sentiment_summary['positive_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['positive']" />
                            <x-metric-card class="metric-panel" label="Sentimen Netral" :value="$sentiment_summary['neutral_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['neutral']" />
                            <x-metric-card class="metric-panel" label="Sentimen Negatif" :value="$sentiment_summary['negative_pct'].'%'" :hint="'Artikel: '.$sentiment_summary['negative']" />
                            <x-metric-card class="metric-panel" label="Sentimen Unavailable" :value="$sentiment_summary['sentiment_unavailable_count']" :hint="'Tidak dihitung ke distribusi'" />
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
                            <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-[14px]">
                                @if($sentiment_summary['top_positive'])
                                    <x-panel padding="p-4" class="panel-frame">
                                        <p class="metric-label">Headline Positif</p>
                                        <p class="headline-card-title">{{ Str::limit($sentiment_summary['top_positive']->title, 80) }}</p>
                                    </x-panel>
                                @endif
                                @if($sentiment_summary['top_negative'])
                                    <x-panel padding="p-4" class="panel-frame">
                                        <p class="metric-label">Headline Negatif</p>
                                        <p class="headline-card-title">{{ Str::limit($sentiment_summary['top_negative']->title, 80) }}</p>
                                    </x-panel>
                                @endif
                            </div>
                        </x-panel>
                    </div>
                </div>

                <div class="dashboard-right-shell" :class="rightPanelOpen ? 'is-open' : 'is-collapsed'">
                    <div class="dashboard-right-column">
                        <x-panel padding="p-5" class="panel-frame dashboard-right-panel-card">
                            <div class="panel-header">
                                <div>
                                    <p class="panel-title">Sentimen</p>
                                    <h3 class="panel-heading">Distribusi</h3>
                                </div>
                            </div>

                            <div class="sentiment-distribution-layout">
                                <div class="sentiment-donut-block">
                                    <div class="sentiment-donut-wrap">
                                        <svg viewBox="0 0 96 96" class="sentiment-donut-chart" aria-label="Distribusi sentimen">
                                            <circle cx="48" cy="48" r="36" class="sentiment-donut-track"></circle>
                                            @foreach($donutSegments as $segment)
                                                @if($segment['length'] > 0)
                                                    <circle
                                                        cx="48"
                                                        cy="48"
                                                        r="36"
                                                        class="sentiment-donut-segment"
                                                        stroke="{{ $segment['color'] }}"
                                                        stroke-dasharray="{{ number_format($segment['length'], 2, '.', '') }} {{ number_format(max($circumference - $segment['length'], 0), 2, '.', '') }}"
                                                        stroke-dashoffset="-{{ number_format($segment['offset'], 2, '.', '') }}">
                                                    </circle>
                                                @endif
                                            @endforeach
                                        </svg>
                                        <div class="sentiment-donut-center">
                                            <span class="sentiment-donut-total">{{ $totalAnalyzed }}</span>
                                            <span class="sentiment-donut-caption">Berita</span>
                                        </div>
                                    </div>
                                </div>

                                <div class="sentiment-legend">
                                    @foreach($sentimentBreakdown as $item)
                                        <div class="sentiment-legend-item">
                                            <span class="sentiment-dot" style="background-color: {{ $item['color'] }}"></span>
                                            <span class="sentiment-legend-label">{{ $item['label'] }}</span>
                                            <span class="sentiment-legend-value">{{ number_format($item['pct'], 1) }}%</span>
                                        </div>
                                    @endforeach
                                </div>

                                <div class="sentiment-progress-list">
                                    @foreach($sentimentBreakdown as $item)
                                        <div class="sentiment-progress-item">
                                            <div class="sentiment-progress-head">
                                                <span class="sentiment-progress-label">{{ $item['label'] }}</span>
                                                <span class="sentiment-progress-count">{{ $item['count'] }}</span>
                                            </div>
                                            <div class="sentiment-progress-bar">
                                                <div class="sentiment-progress-fill" style="width: {{ $item['pct'] }}%; background-color: {{ $item['color'] }}"></div>
                                            </div>
                                        </div>
                                    @endforeach
                                </div>

                                <div class="sentiment-summary-card">
                                    <p class="section-label">Total Berita Dianalisis</p>
                                    <p class="sentiment-summary-value">{{ number_format($totalAnalyzed) }}</p>
                                </div>
                            </div>
                        </x-panel>

                        <x-panel padding="p-5" class="panel-frame dashboard-right-panel-card flex-1 flex flex-col min-h-[360px]" x-data="newsRefresh('{{ $stock->code }}')">
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
                                <span class="news-count text-green-400">▲ {{ $news->where('sentiment_label', 'positive')->count() }} positif</span>
                                <span class="news-count text-amber-400">◆ {{ $news->where('sentiment_label', 'neutral')->count() }} netral</span>
                                <span class="news-count text-rose-400">▼ {{ $news->where('sentiment_label', 'negative')->count() }} negatif</span>
                            </div>

                            <div class="news-list-shell overflow-hidden flex-1">
                                <div class="dashboard-news-scroll max-h-[520px] overflow-y-auto" id="newsContainer">
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
                                               class="news-item group border-b border-white/10 {{ $article->sentiment_label === 'positive' ? 'news-item-positive' : ($article->sentiment_label === 'negative' ? 'news-item-negative' : 'news-item-neutral') }}">
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
            </div>
        </div>
    </div>

    @if($chart_mode === 'internal')
        @push('scripts')
            <script>
                const priceSeries = @json($pricePoints);
                const ctx = document.getElementById('priceChart');
                if (ctx && priceSeries.length) {
                    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 280);
                    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.28)');
                    gradient.addColorStop(1, 'rgba(26, 30, 40, 0)');

                    new window.Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: priceSeries.map(p => p.date),
                            datasets: [{
                                label: 'Close',
                                data: priceSeries.map(p => p.close),
                                borderColor: '#3b82f6',
                                borderWidth: 2,
                                fill: true,
                                backgroundColor: gradient,
                                tension: 0.4,
                                pointRadius: 0,
                            }],
                        },
                        options: {
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { ticks: { color: '#7c8299' }, grid: { display: false } },
                                y: { ticks: { color: '#7c8299' }, grid: { color: 'rgba(255,255,255,0.07)' } },
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
                const srv = document.getElementById('serverArticles');
                const alp = document.getElementById('alpineArticles');
                if (srv) srv.style.display = 'none';
                if (alp) alp.style.display = 'block';

                const now = new Date();
                this.lastRefreshed = 'Diperbarui: ' +
                    now.toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) +
                    ' ' + now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });

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
