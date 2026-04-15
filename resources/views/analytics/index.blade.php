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
                    @php $quote = $liveQuote ?? null; @endphp
                    <div class="flex flex-wrap items-center gap-4 text-sm text-slate-400">
                        <span>Harga: {{ $quote['last'] ?? ($latestPrice?->close ? number_format($latestPrice->close, 2) : '-') }}</span>
                        <span class="{{ ($priceChange ?? 0) >=0 ? 'text-green-400' : 'text-rose-400' }}">Δ {{ $priceChange ? number_format($priceChange, 2) : '0.00' }}%</span>
                        <span>Sentimen rata-rata: {{ $analytics['average_sentiment'] }}</span>
                        <span>Artikel: {{ $summary['total'] }}</span>
                        @if($quote)
                            <span class="text-[11px] px-2 py-1 rounded-full border border-slate-700">{{ $quote['source'] ?? 'live' }} • {{ $quote['is_live'] ? 'Live' : 'Snapshot' }}</span>
                        @endif
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
                <x-metric-card label="Weighted Sentiment" :value="$analytics['weighted_sentiment_stats']['weighted_sentiment_average'] ?? $analytics['weighted_sentiment']" hint="Bobot kualitas (relevance/source) + sumber/headline/recency" />
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
                    @if(($chartData['prices'] ?? collect())->filter()->count() < 5)
                        <p class="text-sm text-slate-400">Data harga belum cukup (minimal 5 hari). Jalankan: <code class="text-slate-300">php artisan stocks:fetch-history</code></p>
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
                        <div class="text-xs text-slate-400">Bobot: Sentimen 20% • Trend 22% • Momentum 18% • Volume/OBV 13% • Volatilitas 12% • Fundamental 15%</div>
                    </div>
                    <p class="text-slate-200 leading-relaxed">{{ $decision['narrative'] }}</p>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                        <x-metric-card label="Return Periode" :value="is_null($decision['price_return']) ? 'N/A' : $decision['price_return'].'%'" />
                        <x-metric-card label="Momentum" :value="$decision['momentum_signal']" />
                        <x-metric-card label="MA Gap" :value="is_null($decision['technical']['ma_gap'] ?? null) ? 'N/A' : number_format(($decision['technical']['ma_gap'])*100,2).'%' " />
                        <x-metric-card label="RSI" :value="$decision['technical']['rsi'] ?? 'N/A'" />
                    </div>

                    {{-- TradingView Chart --}}
                    <div class="glass-card border border-slate-800/80 rounded-2xl overflow-hidden my-6">
                        <div class="flex items-center justify-between px-4 py-3 border-b border-slate-800">
                            <div>
                                <p class="text-xs text-slate-400 uppercase">Chart</p>
                                <h3 class="font-semibold">Tren Harga — {{ $stock->code }}</h3>
                            </div>
                            <x-timeframe-tabs :active="$period" :code="$stock->code" routeName="analytics.index" />
                        </div>
                        <div class="h-80">
                            @php
                                $tvInterval = match($period ?? '30') {
                                    '7'  => 'D',
                                    '30' => 'D',
                                    '90' => 'W',
                                    '180', '365' => 'W',
                                    default => 'D',
                                };
                            @endphp
                            <iframe
                                src="https://s.tradingview.com/widgetembed/?symbol={{ urlencode($stock->tradingview_symbol ?? ('IDX:'.$stock->code)) }}&interval={{ $tvInterval }}&symboledit=0&saveimage=0&toolbarbg=0f172a&studies=[]&theme=dark&style=1&locale=id&hide_top_toolbar=0&hide_legend=0&allow_symbol_change=0"
                                class="w-full h-full"
                                allowtransparency="true"
                                frameborder="0">
                            </iframe>
                        </div>
                    </div>

                    @php $signal = $decision['trading_signal'] ?? null; @endphp
                    @if($signal)
                        <div class="mt-6">
                            <div class="text-xs text-slate-500 uppercase font-medium mb-3">Trading Signal</div>
                            <div class="glass-card border rounded-2xl p-5 mb-4
                                {{ $signal['valid']
                                    ? ($signal['quality'] === 'strong'
                                        ? 'border-green-500/40 bg-green-500/5'
                                        : 'border-sky-500/40 bg-sky-500/5')
                                    : 'border-slate-700 bg-slate-900/50' }}">
                                <div class="flex items-center justify-between mb-4">
                                    <div>
                                        <div class="text-xs text-slate-400 uppercase font-medium">Signal Status</div>
                                        <div class="text-xl font-bold mt-1 {{ $signal['valid'] ? 'text-green-400' : 'text-slate-400' }}">
                                            {{ $signal['valid'] ? '✅ VALID — ENTRY ZONE' : '⏸ WAIT — Belum Ada Signal' }}
                                        </div>
                                        <div class="text-sm text-slate-400 mt-0.5">
                                            Kualitas:
                                            <span class="font-medium {{ $signal['quality'] === 'strong' ? 'text-green-400' : ($signal['quality'] === 'moderate' ? 'text-sky-400' : 'text-slate-400') }}">
                                                {{ strtoupper($signal['quality']) }}
                                            </span>
                                            • {{ $signal['confirm_count'] }} konfirmasi, {{ $signal['warn_count'] }} peringatan
                                        </div>
                                    </div>
                                    <div class="text-right">
                                        <div class="text-xs text-slate-500">R:R Ratio</div>
                                        <div class="text-3xl font-bold {{ $signal['rr_ratio_2r'] >= 2 ? 'text-green-400' : 'text-amber-400' }}">
                                            1:{{ $signal['rr_ratio_2r'] }}
                                        </div>
                                        <div class="text-xs text-slate-500">Target 2R</div>
                                    </div>
                                </div>

                                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                                    <div class="bg-slate-900/80 rounded-xl p-3 border border-slate-800">
                                        <div class="text-[10px] text-slate-500 uppercase mb-1">Entry Zone</div>
                                        <div class="font-mono font-bold text-sky-400 text-lg">
                                            {{ number_format($signal['entry_zone_low']) }}
                                            <span class="text-slate-500 text-sm">–</span>
                                            {{ number_format($signal['entry_zone_high']) }}
                                        </div>
                                        <div class="text-[10px] text-slate-500">Last: {{ number_format($signal['entry']) }}</div>
                                    </div>

                                    <div class="bg-rose-500/5 rounded-xl p-3 border border-rose-500/20">
                                        <div class="text-[10px] text-rose-400 uppercase mb-1">Stop Loss</div>
                                        <div class="font-mono font-bold text-rose-400 text-lg">
                                            {{ number_format($signal['stop_recommended']) }}
                                        </div>
                                        <div class="text-[10px] text-slate-500">
                                            Risk: Rp {{ number_format($signal['risk_per_share']) }}/lembar
                                        </div>
                                    </div>

                                    <div class="bg-green-500/5 rounded-xl p-3 border border-green-500/20">
                                        <div class="text-[10px] text-green-400 uppercase mb-1">Target 1 (2R)</div>
                                        <div class="font-mono font-bold text-green-400 text-lg">
                                            {{ number_format($signal['target_2r']) }}
                                        </div>
                                        <div class="text-[10px] text-slate-500">R:R = 1:{{ $signal['rr_ratio_2r'] }}</div>
                                    </div>

                                <div class="bg-emerald-500/5 rounded-xl p-3 border border-emerald-500/20">
                                    <div class="text-[10px] text-emerald-400 uppercase mb-1">Target 2 (3R)</div>
                                    <div class="font-mono font-bold text-emerald-400 text-lg">
                                        {{ number_format($signal['target_3r']) }}
                                    </div>
                                    <div class="text-[10px] text-slate-500">R:R = 1:{{ $signal['rr_ratio_3r'] }}</div>
                                </div>
                            </div>
                            @if(!empty($signal['target_note']))
                                <div class="text-[11px] text-amber-400 mt-2 flex gap-1">
                                    <span>⚠</span><span>{{ $signal['target_note'] }}</span>
                                </div>
                            @endif

                            @if($signal['valid'] ?? false)
                                <div class="mt-3">
                                    <a href="{{ route('trades.index', [
                                        'stock_id' => $stock->id,
                                        'entry_price' => $signal['entry'],
                                        'stop_loss' => $signal['stop_recommended'],
                                        'target_1' => $signal['target_2r'],
                                        'target_2' => $signal['target_3r'],
                                        'lot_size' => $signal['lot_size'],
                                        'rr_ratio' => $signal['rr_ratio_2r'],
                                        'dss_score' => $decision['final_score'] ?? 0,
                                        'dss_prediction' => $decision['prediction'] ?? 'flat',
                                        'dss_confidence' => $decision['prediction_confidence'] ?? 0,
                                        'signal_quality' => $signal['quality'],
                                        'entry_zone_low' => $signal['entry_zone_low'] ?? null,
                                        'entry_zone_high' => $signal['entry_zone_high'] ?? null,
                                    ]) }}"
                                       class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-500 hover:bg-green-400 text-slate-900 font-semibold text-sm transition">
                                        📝 Catat Trade
                                    </a>
                                </div>
                            @endif

                            <div class="border-t border-slate-800 pt-3 mb-3">
                                <div class="text-xs text-slate-500 uppercase mb-2">
                                    Position Sizing (Modal Rp 10jt • Risk 2%)
                                </div>
                                    <div class="grid grid-cols-3 gap-3">
                                        <div>
                                            <div class="text-[10px] text-slate-500">Lot Size</div>
                                            <div class="font-mono font-bold text-slate-200">
                                                {{ number_format($signal['lot_size']) }} lembar
                                            </div>
                                        </div>
                                        <div>
                                            <div class="text-[10px] text-slate-500">Nilai Posisi</div>
                                            <div class="font-mono font-bold text-slate-200">
                                                Rp {{ number_format($signal['lot_value']) }}
                                            </div>
                                        </div>
                                        <div>
                                            <div class="text-[10px] text-slate-500">Max Loss</div>
                                            <div class="font-mono font-bold text-rose-400">
                                                Rp {{ number_format($signal['risk_amount']) }}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div class="border-t border-slate-800 pt-3 mb-3">
                                    <div class="text-xs text-slate-500 uppercase mb-2">Level Kunci</div>
                                    <div class="flex flex-wrap gap-2 text-[11px]">
                                        @if($signal['vwap'])
                                            <span class="px-2 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-300">
                                                VWAP: {{ number_format($signal['vwap'], 0) }}
                                            </span>
                                        @endif
                                        <span class="px-2 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                                            MA20: {{ number_format($signal['ma20'], 0) }}
                                        </span>
                                        @if($signal['bb_upper'])
                                            <span class="px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
                                                BB Upper: {{ number_format($signal['bb_upper'], 0) }}
                                            </span>
                                        @endif
                                        @if($signal['bb_lower'])
                                            <span class="px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
                                                BB Lower: {{ number_format($signal['bb_lower'], 0) }}
                                            </span>
                                        @endif
                                        <span class="px-2 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-300">
                                            Resistance: {{ number_format($signal['resistance'], 0) }}
                                        </span>
                                        <span class="px-2 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-300">
                                            Support: {{ number_format($signal['support'], 0) }}
                                        </span>
                                    </div>
                                </div>

                                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    @if(count($signal['confirmations']) > 0)
                                        <div>
                                            <div class="text-xs text-green-400 uppercase mb-1">✓ Konfirmasi</div>
                                            <div class="space-y-1">
                                                @foreach($signal['confirmations'] as $c)
                                                    <div class="text-[11px] text-green-300 flex gap-1">
                                                        <span>✓</span><span>{{ $c }}</span>
                                                    </div>
                                                @endforeach
                                            </div>
                                        </div>
                                    @endif

                                    @if(count($signal['warnings']) > 0)
                                        <div>
                                            <div class="text-xs text-amber-400 uppercase mb-1">⚠ Peringatan</div>
                                            <div class="space-y-1">
                                                @foreach($signal['warnings'] as $w)
                                                    <div class="text-[11px] text-amber-300 flex gap-1">
                                                        <span>⚠</span><span>{{ $w }}</span>
                                                    </div>
                                                @endforeach
                                            </div>
                                        </div>
                                    @endif
                                </div>

                                <div class="mt-3 pt-3 border-t border-slate-800">
                                    <p class="text-[10px] text-slate-600">
                                        ⚠ Sinyal bersifat indikatif berdasarkan analisis teknikal dan sentimen.
                                        Bukan rekomendasi investasi. Position sizing asumsi modal Rp 10jt dan risk 2%.
                                    </p>
                                </div>
                            </div>
                        </div>
                    @endif

                    <div class="text-xs text-slate-500 uppercase font-medium mt-6 mb-3">Indikator Teknikal Lanjutan</div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        @php $macd = $decision['indicators']['macd'] ?? null; @endphp
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                            <div class="flex items-center justify-between mb-3">
                                <span class="text-xs text-slate-400 uppercase font-medium">MACD</span>
                                @if($macd)
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium {{ $macd['trend'] === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : ($macd['trend'] === 'bearish' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                        {{ strtoupper($macd['trend']) }}
                                    </span>
                                @endif
                            </div>
                            @if($macd)
                                <div class="space-y-1.5 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">MACD</span>
                                        <span class="font-mono {{ $macd['macd'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">{{ number_format($macd['macd'], 4) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Signal</span>
                                        <span class="font-mono text-slate-200">{{ number_format($macd['signal'], 4) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Histogram</span>
                                        <span class="font-mono {{ $macd['histogram'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                                            {{ $macd['histogram'] >= 0 ? '▲' : '▼' }} {{ number_format(abs($macd['histogram']), 4) }}
                                        </span>
                                    </div>
                                </div>
                            @else
                                <p class="text-xs text-slate-500">Butuh minimal 35 candle untuk menghitung MACD. Jalankan stocks:sync-live untuk menambah data.</p>
                            @endif
                        </div>

                        @php $bb = $decision['indicators']['bollinger'] ?? null; @endphp
                        @if($bb)
                            <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                                <div class="flex items-center justify-between mb-3">
                                    <span class="text-xs text-slate-400 uppercase font-medium">Bollinger Bands</span>
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium {{ $bb['position'] === 'oversold' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : ($bb['position'] === 'overbought' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                        {{ strtoupper($bb['position']) }}
                                    </span>
                                </div>
                                <div class="space-y-1.5 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Upper</span>
                                        <span class="font-mono text-rose-400">{{ number_format($bb['upper'], 2) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Middle</span>
                                        <span class="font-mono text-slate-200">{{ number_format($bb['middle'], 2) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Lower</span>
                                        <span class="font-mono text-green-400">{{ number_format($bb['lower'], 2) }}</span>
                                    </div>
                                    <div class="flex justify-between border-t border-slate-800 pt-1.5 mt-1.5">
                                        <span class="text-slate-500 text-xs">%B: {{ number_format($bb['percent_b'], 2) }}</span>
                                        <span class="text-slate-500 text-xs">BW: {{ number_format($bb['bandwidth'], 1) }}%</span>
                                    </div>
                                </div>
                            </div>
                        @endif

                        @php $stoch = $decision['indicators']['stochastic'] ?? null; @endphp
                        @if($stoch)
                            <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                                <div class="flex items-center justify-between mb-3">
                                    <span class="text-xs text-slate-400 uppercase font-medium">Stochastic %K/%D</span>
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium {{ $stoch['signal'] === 'oversold' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : ($stoch['signal'] === 'overbought' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                        {{ strtoupper($stoch['signal']) }}
                                    </span>
                                </div>
                                <div class="space-y-2 text-sm">
                                    <div>
                                        <div class="flex justify-between mb-1">
                                            <span class="text-slate-400">%K (Fast)</span>
                                            <span class="font-mono {{ $stoch['k'] < 20 ? 'text-green-400' : ($stoch['k'] > 80 ? 'text-rose-400' : 'text-slate-200') }}">{{ number_format($stoch['k'], 2) }}</span>
                                        </div>
                                        <div class="w-full bg-slate-800 rounded-full h-1.5">
                                            <div class="h-1.5 rounded-full {{ $stoch['k'] < 20 ? 'bg-green-500' : ($stoch['k'] > 80 ? 'bg-rose-500' : 'bg-sky-500') }}" style="width: {{ min(100, max(0, $stoch['k'])) }}%"></div>
                                        </div>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">%D (Signal)</span>
                                        <span class="font-mono text-slate-300">{{ number_format($stoch['d'], 2) }}</span>
                                    </div>
                                    @if($stoch['cross'])
                                        <div class="text-xs {{ $stoch['cross'] === 'bullish' ? 'text-green-400' : 'text-rose-400' }}">
                                            {{ $stoch['cross'] === 'bullish' ? '▲ Bullish crossover' : '▼ Bearish crossover' }}
                                        </div>
                                    @endif
                                </div>
                            </div>
                        @endif

                        @php $obv = $decision['indicators']['obv'] ?? null; @endphp
                        @if($obv)
                            <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                                <div class="flex items-center justify-between mb-3">
                                    <span class="text-xs text-slate-400 uppercase font-medium">OBV</span>
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium {{ $obv['obv_trend'] === 'rising' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : ($obv['obv_trend'] === 'falling' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                        {{ strtoupper($obv['obv_trend']) }}
                                    </span>
                                </div>
                                <div class="space-y-1.5 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">OBV</span>
                                        <span class="font-mono text-slate-200">{{ number_format($obv['obv']) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Trend</span>
                                        <span class="{{ $obv['obv_trend'] === 'rising' ? 'text-green-400' : ($obv['obv_trend'] === 'falling' ? 'text-rose-400' : 'text-slate-400') }}">
                                            {{ $obv['obv_trend'] === 'rising' ? '▲ Rising' : ($obv['obv_trend'] === 'falling' ? '▼ Falling' : '→ Neutral') }}
                                        </span>
                                    </div>
                                    @if($obv['divergence'])
                                        <div class="flex justify-between border-t border-slate-800 pt-1.5 mt-1.5">
                                            <span class="text-slate-400">Divergence</span>
                                            <span class="text-xs font-medium {{ $obv['divergence'] === 'bullish' ? 'text-green-400' : 'text-rose-400' }}">{{ ucfirst($obv['divergence']) }}</span>
                                        </div>
                                    @endif
                                </div>
                            </div>
                        @endif
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
                    <div class="text-xs text-slate-500 uppercase font-medium mt-6 mb-3">Indikator Fase 2 — Trend Strength & Volatilitas</div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        @php $adx = $decision['indicators']['adx'] ?? null; @endphp
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                            <div class="flex items-center justify-between mb-3">
                                <span class="text-xs text-slate-400 uppercase font-medium">ADX</span>
                                @if($adx)
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium {{ $adx['strength'] === 'strong'
                                        ? ($adx['direction'] === 'bullish'
                                            ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/30')
                                        : 'bg-slate-800 text-slate-400 border border-slate-700' }}">
                                        {{ strtoupper($adx['strength']) }}
                                    </span>
                                @endif
                            </div>
                            @if($adx)
                                <div class="space-y-2 text-sm">
                                    <div>
                                        <div class="flex justify-between mb-1">
                                            <span class="text-slate-400">ADX</span>
                                            <span class="font-mono font-bold {{ $adx['adx'] > 40 ? 'text-amber-400' : ($adx['adx'] > 25 ? 'text-sky-400' : 'text-slate-400') }}">
                                                {{ number_format($adx['adx'], 2) }}
                                            </span>
                                        </div>
                                        <div class="w-full bg-slate-800 rounded-full h-1.5">
                                            <div class="h-1.5 rounded-full {{ $adx['adx'] > 40 ? 'bg-amber-500' : ($adx['adx'] > 25 ? 'bg-sky-500' : 'bg-slate-600') }}"
                                                 style="width: {{ min(100, $adx['adx']) }}%"></div>
                                        </div>
                                        <div class="flex justify-between text-[10px] text-slate-600 mt-0.5">
                                            <span>Weak</span><span>25</span><span>Strong 40+</span>
                                        </div>
                                    </div>
                                    <div class="flex justify-between border-t border-slate-800 pt-2">
                                        <div class="text-center">
                                            <div class="text-[10px] text-slate-500 mb-0.5">+DI</div>
                                            <div class="font-mono text-green-400">{{ number_format($adx['plus_di'], 2) }}</div>
                                        </div>
                                        <div class="text-center">
                                            <div class="text-[10px] text-slate-500 mb-0.5">Direction</div>
                                            <div class="{{ $adx['direction'] === 'bullish' ? 'text-green-400' : 'text-rose-400' }}">
                                                {{ $adx['direction'] === 'bullish' ? '▲ Bullish' : '▼ Bearish' }}
                                            </div>
                                        </div>
                                        <div class="text-center">
                                            <div class="text-[10px] text-slate-500 mb-0.5">-DI</div>
                                            <div class="font-mono text-rose-400">{{ number_format($adx['minus_di'], 2) }}</div>
                                        </div>
                                    </div>
                                </div>
                            @else
                                <p class="text-xs text-slate-500">Butuh minimal 28 candle untuk ADX.</p>
                            @endif
                        </div>

                        @php $atr = $decision['indicators']['atr'] ?? null; @endphp
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                            <div class="flex items-center justify-between mb-3">
                                <span class="text-xs text-slate-400 uppercase font-medium">ATR (Volatilitas)</span>
                                @if($atr)
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium
                                      {{ $atr['volatility'] === 'high'
                                         ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                                         : ($atr['volatility'] === 'low'
                                            ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                                            : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                      {{ strtoupper($atr['volatility']) }}
                                    </span>
                                @endif
                            </div>
                            @if($atr)
                                <div class="space-y-1.5 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">ATR (abs)</span>
                                        <span class="font-mono text-slate-200">{{ number_format($atr['atr'], 2) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">ATR %</span>
                                        <span class="font-mono font-bold
                                          {{ $atr['atr_percent'] > 3 ? 'text-rose-400' : ($atr['atr_percent'] < 1 ? 'text-green-400' : 'text-amber-400') }}">
                                          {{ number_format($atr['atr_percent'], 2) }}%
                                        </span>
                                    </div>
                                    <div class="text-[11px] text-slate-500 border-t border-slate-800 pt-2">
                                        @if($atr['volatility'] === 'high')
                                            ⚠ Volatilitas tinggi — pertimbangkan stop-loss lebih lebar
                                        @elseif($atr['volatility'] === 'low')
                                            ✓ Volatilitas terkontrol — momentum lebih stabil
                                        @else
                                            Volatilitas normal
                                        @endif
                                    </div>
                                </div>
                            @else
                                <p class="text-xs text-slate-500">Butuh minimal 15 candle untuk ATR.</p>
                            @endif
                        </div>

                        @php $vwap = $decision['indicators']['vwap'] ?? null; @endphp
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                            <div class="flex items-center justify-between mb-3">
                                <span class="text-xs text-slate-400 uppercase font-medium">VWAP</span>
                                @if($vwap)
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium
                                      {{ $vwap['position'] === 'above'
                                         ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                                         : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                                      {{ strtoupper($vwap['position']) }} VWAP
                                    </span>
                                @endif
                            </div>
                            @if($vwap)
                                <div class="space-y-1.5 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">VWAP</span>
                                        <span class="font-mono text-slate-200">{{ number_format($vwap['vwap'], 2) }}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-400">Jarak dari VWAP</span>
                                        <span class="font-mono font-bold {{ $vwap['position'] === 'above' ? 'text-green-400' : 'text-rose-400' }}">
                                            {{ $vwap['position'] === 'above' ? '+' : '-' }}{{ number_format($vwap['distance'], 2) }}%
                                        </span>
                                    </div>
                                    <div class="text-[11px] text-slate-500 border-t border-slate-800 pt-2">
                                        {{ $vwap['position'] === 'above'
                                             ? 'Harga di atas VWAP — bias bullish, buyer in control'
                                             : 'Harga di bawah VWAP — bias bearish, seller in control' }}
                                    </div>
                                </div>
                            @else
                                <p class="text-xs text-slate-500">Butuh minimal 5 candle untuk VWAP.</p>
                            @endif
                        </div>

                        @php $candles = $decision['indicators']['candles'] ?? null; @endphp
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
                            <div class="flex items-center justify-between mb-3">
                                <span class="text-xs text-slate-400 uppercase font-medium">Pola Candlestick</span>
                                @if($candles)
                                    <span class="px-2 py-0.5 rounded-full text-[11px] font-medium
                                      {{ $candles['signal'] === 'bullish'
                                         ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                                         : ($candles['signal'] === 'bearish'
                                            ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                                            : 'bg-slate-800 text-slate-400 border border-slate-700') }}">
                                      {{ strtoupper($candles['signal']) }}
                                    </span>
                                @endif
                            </div>
                            @if($candles)
                                @if(($candles['count'] ?? 0) > 0)
                                    <div class="space-y-2">
                                        @foreach($candles['patterns'] as $pattern)
                                            <div class="flex items-start gap-2 p-2 rounded-lg
                                                {{ $pattern['signal'] === 'bullish'
                                                    ? 'bg-green-500/5 border border-green-500/20'
                                                    : ($pattern['signal'] === 'bearish'
                                                        ? 'bg-rose-500/5 border border-rose-500/20'
                                                        : 'bg-slate-800/50 border border-slate-700') }}">
                                                <span class="text-sm">
                                                    {{ $pattern['signal'] === 'bullish' ? '▲' : ($pattern['signal'] === 'bearish' ? '▼' : '◆') }}
                                                </span>
                                                <div>
                                                    <div class="text-sm font-medium
                                                        {{ $pattern['signal'] === 'bullish' ? 'text-green-400' : ($pattern['signal'] === 'bearish' ? 'text-rose-400' : 'text-slate-300') }}">
                                                        {{ $pattern['name'] }}
                                                    </div>
                                                    <div class="text-[11px] text-slate-500">{{ $pattern['description'] }}</div>
                                                </div>
                                            </div>
                                        @endforeach
                                    </div>
                                @else
                                    <div class="text-center py-3">
                                        <div class="text-slate-500 text-sm">Tidak ada pola signifikan</div>
                                        <div class="text-[11px] text-slate-600 mt-1">pada 3 candle terakhir</div>
                                    </div>
                                @endif
                            @else
                                <p class="text-xs text-slate-500">Butuh minimal 3 candle.</p>
                            @endif
                        </div>
                    </div>

                    <div class="text-xs text-slate-500 uppercase font-medium mt-6 mb-3">Analisis Fundamental</div>
                    @php $fundamental = $decision['indicators']['fundamental'] ?? null; @endphp
                    @if($fundamental)
                        <div class="glass-card border border-slate-800/80 rounded-2xl p-5">
                            <div class="flex items-center justify-between mb-4">
                                <div>
                                    <span class="text-xs text-slate-400 uppercase font-medium">Fundamental Score</span>
                                    <div class="text-2xl font-bold mt-1 {{ $fundamental['score'] >= 70 ? 'text-green-400' : ($fundamental['score'] >= 55 ? 'text-slate-200' : ($fundamental['score'] <= 35 ? 'text-rose-400' : 'text-amber-400')) }}">
                                        {{ $fundamental['score'] }}/100
                                    </div>
                                </div>
                                <span class="px-3 py-1 rounded-full text-sm font-medium {{ $fundamental['rating'] === 'attractive'
                                    ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                                    : ($fundamental['rating'] === 'expensive'
                                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                                        : 'bg-slate-800 text-slate-300 border border-slate-700') }}">
                                    {{ strtoupper($fundamental['rating']) }}
                                </span>
                            </div>
                            <div class="w-full bg-slate-800 rounded-full h-2 mb-4">
                                <div class="h-2 rounded-full {{ $fundamental['score'] >= 70 ? 'bg-green-500' : ($fundamental['score'] >= 55 ? 'bg-sky-500' : ($fundamental['score'] <= 35 ? 'bg-rose-500' : 'bg-amber-500')) }}"
                                     style="width: {{ $fundamental['score'] }}%"></div>
                            </div>
                            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">PBV</div>
                                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fundamental['pbv'] !== null ? number_format($fundamental['pbv'], 1).'x' : 'N/A' }}</div>
                                    <div class="text-[10px] text-slate-500">Price / Book</div>
                                </div>
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">PER</div>
                                    <div class="text-lg font-mono font-bold {{ $fundamental['per'] && $fundamental['per'] < 15 ? 'text-green-400' : ($fundamental['per'] && $fundamental['per'] > 25 ? 'text-rose-400' : 'text-slate-100') }}">
                                        {{ $fundamental['per'] !== null && $fundamental['per'] > 0 ? number_format($fundamental['per'], 1).'x' : 'N/A' }}
                                    </div>
                                    <div class="text-[10px] text-slate-500">Price / Earnings</div>
                                </div>
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">ROE</div>
                                    <div class="text-lg font-mono font-bold {{ $fundamental['roe'] && $fundamental['roe'] >= 15 ? 'text-green-400' : ($fundamental['roe'] && $fundamental['roe'] < 0 ? 'text-rose-400' : 'text-slate-100') }}">
                                        {{ $fundamental['roe'] !== null ? number_format($fundamental['roe'], 1).'%' : 'N/A' }}
                                    </div>
                                    <div class="text-[10px] text-slate-500">Return on Equity</div>
                                </div>
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">DER</div>
                                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fundamental['der'] !== null ? number_format($fundamental['der'], 1).'x' : 'N/A' }}</div>
                                    <div class="text-[10px] text-slate-500">Debt / Equity</div>
                                </div>
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">EPS</div>
                                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fundamental['eps'] !== null ? 'Rp '.number_format($fundamental['eps'], 0) : 'N/A' }}</div>
                                    <div class="text-[10px] text-slate-500">Earnings / Share</div>
                                </div>
                                <div class="bg-slate-900/50 rounded-xl p-3">
                                    <div class="text-[10px] text-slate-500 uppercase mb-1">Div. Yield</div>
                                    <div class="text-lg font-mono font-bold {{ $fundamental['dividend_yield'] && $fundamental['dividend_yield'] >= 5 ? 'text-green-400' : 'text-slate-100' }}">
                                        {{ $fundamental['dividend_yield'] !== null ? number_format($fundamental['dividend_yield'], 1).'%' : 'N/A' }}
                                    </div>
                                    <div class="text-[10px] text-slate-500">Dividend Yield</div>
                                </div>
                            </div>
                            @if(count($fundamental['signals'] ?? []) > 0)
                                <div class="space-y-1 mb-3">
                                    @foreach($fundamental['signals'] as $sig)
                                        <div class="flex items-start gap-2 text-sm text-green-400">
                                            <span>✓</span><span>{{ $sig }}</span>
                                        </div>
                                    @endforeach
                                </div>
                            @endif
                            @if(count($fundamental['risks'] ?? []) > 0)
                                <div class="space-y-1">
                                    @foreach($fundamental['risks'] as $risk)
                                        <div class="flex items-start gap-2 text-sm text-rose-400">
                                            <span>⚠</span><span>{{ $risk }}</span>
                                        </div>
                                    @endforeach
                                </div>
                            @endif
                            @if($fundamental['updated_at'])
                                <div class="text-[10px] text-slate-600 mt-3 text-right">
                                    Data per: {{ \Illuminate\Support\Carbon::parse($fundamental['updated_at'])->format('Y-m-d') }}
                                </div>
                            @endif
                        </div>
                    @endif
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
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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

            @if(!empty($ts))
            const internalCtx = document.getElementById('internalChart');
            if (internalCtx) {
                const labels2   = @json($chartLabels ?? []);
                const closes2   = @json($chartClose ?? []);
                const ma5data   = @json($ma5data ?? []);
                const ma20data  = @json($ma20data ?? []);
                const entryVal  = {{ $ts['entry_ideal'] ?? 'null' }};
                const stopVal   = {{ $ts['stop_loss'] ?? 'null' }};
                const targetVal = {{ $ts['target_1'] ?? 'null' }};

                const makeLine = (val) => (val !== null && labels2.length) ? labels2.map(() => val) : [];

                new window.Chart(internalCtx, {
                    type: 'line',
                    data: {
                        labels: labels2,
                        datasets: [
                            { label: 'Harga', data: closes2, borderColor: '#94a3b8', backgroundColor: 'rgba(148,163,184,0.15)', borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: true },
                            { label: 'MA5', data: ma5data, borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false },
                            { label: 'MA20', data: ma20data, borderColor: '#fbbf24', borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false },
                            { label: 'Entry', data: makeLine(entryVal), borderColor: '#38bdf8', borderWidth: 1, borderDash: [6,3], pointRadius: 0, fill: false },
                            { label: 'Stop', data: makeLine(stopVal), borderColor: '#f43f5e', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false },
                            { label: 'Target', data: makeLine(targetVal), borderColor: '#22c55e', borderWidth: 1, borderDash: [6,3], pointRadius: 0, fill: false },
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { 
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y ? ctx.parsed.y.toLocaleString('id-ID') : '-'}`
                                }
                            }
                        },
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { grid: { color: 'rgba(148,163,184,0.06)' }, ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 10 } },
                            y: { grid: { color: 'rgba(148,163,184,0.06)' }, ticks: { color: '#64748b', font: { size: 10 }, callback: (v) => v.toLocaleString('id-ID') } },
                        },
                    }
                });
            }
            @endif
        </script>
    @endpush
</x-app-layout>
