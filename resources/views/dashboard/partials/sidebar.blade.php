<x-panel class="sticky top-24" x-data>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div>
            <p class="text-xs text-slate-400 uppercase">Watchlist</p>
            <h3 class="text-lg font-semibold">Pergerakan Cepat</h3>
        </div>
        <div class="flex items-center gap-2 text-xs flex-wrap justify-end">
            <a href="{{ route('dashboard') }}" class="px-3 py-1 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-slate-600 transition whitespace-nowrap">Dashboard</a>
            <a href="{{ route('watchlist.index') }}" class="px-3 py-1 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-slate-600 transition whitespace-nowrap">Watchlist</a>
            <button type="button" class="px-2 py-1 rounded-lg border border-slate-700 bg-slate-800/70 hover:border-slate-600 transition flex items-center gap-1 whitespace-nowrap"
                    x-on:click="$dispatch('toggle-watchlist')">
                <span x-text="$root.__watchlistOpen ? 'Sembunyikan' : 'Tampilkan'"></span>
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m9 5 7 7-7 7" :transform="$root.__watchlistOpen ? 'rotate(180 12 12)' : ''"/>
                </svg>
            </button>
        </div>
    </div>
    @php
        $tvMode = config('dashboard.stock_chart_mode', env('STOCK_CHART_MODE', 'internal')) === 'tradingview';
        $symbols = ($watchlistInsights ?? collect())->pluck('stock.code')->filter()->take(10)->values();
    @endphp
    @if($tvMode && $symbols->isNotEmpty())
        <div class="rounded-xl border border-slate-800/80 bg-slate-900/60 p-2 mb-3">
            <div class="tradingview-widget-container">
                <div class="tradingview-widget-container__widget"></div>
                <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
                {
                    "symbols": [
                        @foreach($symbols as $sym)
                            { "proName": "{{ config('dashboard.tradingview_exchange', 'IDX') }}:{{ $sym }}", "title": "{{ $sym }}" }@if(!$loop->last),@endif
                        @endforeach
                    ],
                    "colorTheme": "dark",
                    "isTransparent": true,
                    "displayMode": "adaptive",
                    "locale": "en"
                }
                </script>
            </div>
        </div>
    @endif
    @php
        $entries = ($watchlistInsights ?? collect());
        if ($entries->isEmpty() && isset($watchlist)) {
            $entries = $watchlist->map(fn($stock) => [
                'stock' => $stock,
                'latest' => $stock->latestPrice,
                'decision' => ['status' => 'Wait and See', 'confidence' => 'Rendah'],
                'sparkline' => collect(),
            ]);
        }
    @endphp
    <div class="space-y-3">
        @forelse($entries as $row)
            @php
                $stock = $row['stock'];
                $latest = $row['latest'] ?? null;
                $decision = $row['decision'] ?? ['status' => 'Wait and See', 'confidence' => 'Rendah'];
                $spark = $row['sparkline'] ?? collect();
                $statusColor = match($decision['status']) {
                    'Bullish Support' => 'text-green-300',
                    'Warning' => 'text-rose-300',
                    default => 'text-amber-300',
                };
            @endphp
            @php
                $initPrice = $latest?->close ?? 0;
                $initChange = ($latest && $latest->open) ? (($latest->close - $latest->open) / $latest->open) * 100 : 0;
            @endphp
            <div class="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2 hover:border-slate-600/80 hover:bg-slate-900/40 transition"
                 x-data="stockTicker('{{ $stock->code }}', {{ $initPrice }}, {{ $initChange }})">
                <div class="w-2/3">
                    <div class="flex items-center justify-between">
                        <div class="font-semibold">{{ $stock->code }}</div>
                        <span class="text-[11px] {{ $statusColor }}">{{ $decision['status'] }}</span>
                    </div>
                    <div class="text-[11px] text-slate-400">{{ \Illuminate\Support\Str::limit($stock->company_name, 28) }}</div>
                    <div class="flex items-end gap-1 h-8 mt-1">
                        @forelse($spark as $val)
                            @php
                                $h = max(5, min(28, (abs($val) * 24) + 5));
                                $c = $val >= 0 ? 'bg-green-400' : 'bg-rose-400';
                            @endphp
                            <div class="w-1.5 rounded-full {{ $c }}" style="height: {{ $h }}px"></div>
                        @empty
                            <span class="text-[10px] text-slate-500">-</span>
                        @endforelse
                    </div>
                </div>
                <div class="text-right w-1/3 space-y-0.5">
                    <div class="font-semibold" x-text="formatPrice(price)">{{ $latest?->close ? number_format($latest->close, 2) : '-' }}</div>
                    <div class="text-xs {{ ($initChange ?? 0) >= 0 ? 'text-green-400' : 'text-rose-400' }}"
                         :class="changePercent >= 0 ? 'text-green-400' : 'text-rose-400'"
                         x-text="formatPercent(changePercent)">
                        {{ $initChange >= 0 ? '+' : '' }}{{ number_format($initChange, 2) }}%
                    </div>
                    <div class="text-[10px]">
                        <span class="px-1.5 py-0.5 rounded-full border text-[10px]"
                              :class="isLive ? 'bg-green-500/10 text-green-400 border-green-500/30' : 'bg-slate-800 text-slate-500 border-slate-700'">
                            <span x-text="isLive ? 'Live' : 'Snap'">{{ $latest?->price_date ? 'Snap' : '' }}</span>
                        </span>
                    </div>
                    <a href="{{ route('analytics.index', ['code' => $stock->code]) }}" class="text-[11px] text-sky-400 block">Analytics</a>
                </div>
            </div>
        @empty
            <p class="text-sm text-slate-400">Belum ada saham di watchlist atau data belum siap. Tambahkan emiten untuk mulai memantau.</p>
        @endforelse
    </div>
    <div class="mt-4">
        <p class="text-xs text-slate-400 uppercase mb-2">Saham Populer</p>
        <div class="space-y-2">
            @foreach($stocks->take(5) as $popular)
                <a href="{{ route('stocks.show', $popular->code) }}" class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-800/60 transition">
                    <div>
                        <div class="font-semibold">{{ $popular->code }}</div>
                        <div class="text-[11px] text-slate-500">{{ $popular->sector }}</div>
                    </div>
                    <span class="text-[10px] text-slate-500">Detail</span>
                </a>
            @endforeach
        </div>
    </div>
</x-panel>
