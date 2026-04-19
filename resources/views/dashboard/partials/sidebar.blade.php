<x-panel class="panel-frame sticky top-24 dashboard-watchlist-panel" x-data>
    <div class="panel-header">
        <div>
            <p class="panel-title">Watchlist</p>
            <h3 class="panel-heading">Portofolio Pantau</h3>
        </div>
    </div>
    @php
        $entries = ($watchlistInsights ?? collect());
        if ($entries->isEmpty() && isset($watchlist)) {
            $entries = $watchlist->map(fn($stock) => [
                'stock' => $stock,
                'latest' => $stock->latestPrice,
                'decision' => ['status' => 'Hold', 'confidence' => 'Rendah'],
                'sparkline' => collect(),
            ]);
        }
    @endphp
    <div class="space-y-3">
        @forelse($entries as $row)
            @php
                $stock = $row['stock'];
                $latest = $row['latest'] ?? null;
                $decision = $row['decision'] ?? ['status' => 'Hold', 'confidence' => 'Rendah'];
                $spark = $row['sparkline'] ?? collect();
                $signal = match($decision['status']) {
                    'Bullish Support', 'BUY', 'Buy' => ['label' => 'BUY', 'class' => 'watchlist-status watchlist-status-buy'],
                    'Warning', 'SELL', 'Sell' => ['label' => 'SELL', 'class' => 'watchlist-status watchlist-status-sell'],
                    default => ['label' => 'HOLD', 'class' => 'watchlist-status watchlist-status-hold'],
                };
            @endphp
            @php
                $initPrice = $latest?->close ?? 0;
                $initChange = ($latest && $latest->open) ? (($latest->close - $latest->open) / $latest->open) * 100 : 0;
            @endphp
            <div class="watchlist-item flex items-center justify-between"
                 x-data="stockTicker('{{ $stock->code }}', {{ $initPrice }}, {{ $initChange }})">
                <div class="w-2/3">
                    <div class="flex items-center justify-between">
                        <div class="watchlist-symbol">{{ $stock->code }}</div>
                        <span class="{{ $signal['class'] }}">{{ $signal['label'] }}</span>
                    </div>
                    <div class="watchlist-name">{{ \Illuminate\Support\Str::limit($stock->company_name, 28) }}</div>
                    <div class="flex items-end gap-1 h-8 mt-1">
                        @forelse($spark as $val)
                            @php
                                $h = max(5, min(28, (abs($val) * 24) + 5));
                                $c = $val >= 0 ? 'watchlist-spark-up' : 'watchlist-spark-down';
                            @endphp
                            <div class="w-1.5 rounded-full {{ $c }}" style="height: {{ $h }}px"></div>
                        @empty
                            <span class="watchlist-name">-</span>
                        @endforelse
                    </div>
                </div>
                <div class="text-right w-1/3 space-y-0.5">
                    <div class="watchlist-price" x-text="formatPrice(price)">{{ $latest?->close ? number_format($latest->close, 2) : '-' }}</div>
                    <div class="watchlist-change {{ ($initChange ?? 0) >= 0 ? 'text-green-400' : 'text-rose-400' }}"
                         :class="changePercent >= 0 ? 'text-green-400' : 'text-rose-400'"
                         x-text="formatPercent(changePercent)">
                        {{ $initChange >= 0 ? '+' : '' }}{{ number_format($initChange, 2) }}%
                    </div>
                    <div class="watchlist-live-wrap">
                        <span class="status-badge"
                              :class="isLive ? 'status-badge-live' : 'status-badge-closed'">
                            <span x-text="isLive ? 'Live' : 'Snap'">{{ $latest?->price_date ? 'Snap' : '' }}</span>
                        </span>
                    </div>
                    <a href="{{ route('analytics.index', ['code' => $stock->code]) }}" class="watchlist-link block">Analytics</a>
                </div>
            </div>
        @empty
            <p class="watchlist-empty">Belum ada saham di watchlist atau data belum siap. Tambahkan emiten untuk mulai memantau.</p>
        @endforelse
    </div>
    <div class="mt-4">
        <p class="section-label mb-2">Saham Populer</p>
        <div class="space-y-2">
            @foreach($stocks->take(5) as $popular)
                <a href="{{ route('stocks.show', $popular->code) }}" class="popular-stock-item flex items-center justify-between">
                    <div>
                        <div class="watchlist-symbol">{{ $popular->code }}</div>
                        <div class="popular-stock-sector">{{ $popular->sector }}</div>
                    </div>
                    <span class="popular-stock-detail">Detail</span>
                </a>
            @endforeach
        </div>
    </div>
</x-panel>
