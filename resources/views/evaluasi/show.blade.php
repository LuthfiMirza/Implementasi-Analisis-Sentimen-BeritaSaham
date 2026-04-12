<x-app-layout>
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div class="flex items-center justify-between gap-3">
            <div>
                <a href="{{ route('evaluasi.index') }}" class="text-sky-400 text-sm hover:underline">← Kembali ke Evaluasi</a>
                <h1 class="text-2xl font-bold text-slate-100 mt-1">{{ $stock->code }} — {{ $stock->company_name }}</h1>
                <p class="text-sm text-slate-400">{{ $stock->sector }} • Analisis {{ now()->format('d M Y') }}</p>
            </div>
            <span class="px-3 py-1 rounded-full text-sm bg-slate-800 text-slate-200 border border-slate-700">
                {{ $articles->count() }} berita • {{ count($prices) }} harga
            </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <x-panel class="p-4">
                @php
                    $score = $result['final_score'] ?? 0;
                    $statusColor = $score >= 60 ? 'text-green-400' : ($score >= 45 ? 'text-amber-400' : 'text-rose-400');
                @endphp
                <div class="text-xs text-slate-400 uppercase">Final Score</div>
                <div class="text-3xl font-bold {{ $statusColor }}">{{ number_format($score, 1) }}</div>
                <div class="mt-2">
                    <span class="px-2 py-0.5 rounded-full text-xs border border-slate-700 text-slate-200">
                        {{ $result['status'] ?? 'N/A' }}
                    </span>
                </div>
            </x-panel>
            <x-panel class="p-4">
                @php
                    $pred = $result['prediction'] ?? 'flat';
                    $predLabel = $pred === 'up' ? '▲ UP' : ($pred === 'down' ? '▼ DOWN' : '→ FLAT');
                    $predClass = $pred === 'up' ? 'text-green-400' : ($pred === 'down' ? 'text-rose-400' : 'text-slate-300');
                    $conf = round(($result['prediction_confidence'] ?? 0) * 100, 1);
                @endphp
                <div class="text-xs text-slate-400 uppercase">Prediksi</div>
                <div class="text-2xl font-semibold {{ $predClass }}">{{ $predLabel }}</div>
                <div class="text-sm text-slate-300 mt-1">Confidence: {{ $conf }}%</div>
                <div class="text-[11px] text-slate-500">Metode: {{ $result['prediction_method'] ?? 'scoring' }}</div>
            </x-panel>
            <x-panel class="p-4">
                @php
                    $sentAvg = $result['sentiment_average'] ?? ($result['prediction_features']['sentiment_average'] ?? 0);
                @endphp
                <div class="text-xs text-slate-400 uppercase">Sentimen Berita</div>
                <div class="text-2xl font-semibold {{ $sentAvg > 0 ? 'text-green-400' : ($sentAvg < 0 ? 'text-rose-400' : 'text-slate-200') }}">
                    {{ number_format($sentAvg, 3) }}
                </div>
                <div class="text-sm text-slate-300">Jumlah berita: {{ $articles->count() }}</div>
                <div class="text-[11px] text-slate-500">Dominansi: {{ $result['sentiment_dominance'] ?? '-' }}</div>
            </x-panel>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="bg-green-500/5 border border-green-500/20 rounded-2xl p-5">
                <div class="text-xs text-green-400 uppercase font-medium mb-2">🟢 Skenario Bullish</div>
                <p class="text-sm text-slate-300 leading-relaxed">{{ $result['scenario_bullish'] ?? '-' }}</p>
            </div>
            <div class="bg-slate-800/50 border border-slate-700 rounded-2xl p-5">
                <div class="text-xs text-slate-400 uppercase font-medium mb-2">⚪ Skenario Netral</div>
                <p class="text-sm text-slate-300 leading-relaxed">{{ $result['scenario_neutral'] ?? '-' }}</p>
            </div>
            <div class="bg-rose-500/5 border border-rose-500/20 rounded-2xl p-5">
                <div class="text-xs text-rose-400 uppercase font-medium mb-2">🔴 Skenario Bearish</div>
                <p class="text-sm text-slate-300 leading-relaxed">{{ $result['scenario_bearish'] ?? '-' }}</p>
            </div>
        </div>

        @php $signal = $result['trading_signal'] ?? null; @endphp
        @if($signal)
            @if($signal['valid'])
                <div class="glass-card border border-green-500/30 bg-green-500/5 rounded-2xl p-4">
                    <div class="flex items-center justify-between mb-3">
                        <div class="text-xs text-green-400 uppercase font-medium">✅ Trading Signal — {{ strtoupper($signal['quality']) }}</div>
                        <span class="text-sm font-bold text-green-400">R:R 1:{{ $signal['rr_ratio_2r'] }}</span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                        <div>
                            <div class="text-[10px] text-slate-500">Entry</div>
                            <div class="font-mono font-bold text-sky-400">{{ number_format($signal['entry']) }}</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-slate-500">Stop</div>
                            <div class="font-mono font-bold text-rose-400">{{ number_format($signal['stop_recommended']) }}</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-slate-500">Target 2R</div>
                            <div class="font-mono font-bold text-green-400">{{ number_format($signal['target_2r']) }}</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-slate-500">Target 3R</div>
                            <div class="font-mono font-bold text-emerald-400">{{ number_format($signal['target_3r']) }}</div>
                        </div>
                    </div>
                </div>
            @else
                <div class="border border-slate-700 bg-slate-900/50 rounded-2xl p-4">
                    <div class="text-xs text-slate-500 uppercase">⏸ Trading Signal — {{ strtoupper($signal['quality']) }}</div>
                    <div class="text-sm text-slate-400 mt-1">
                        {{ $signal['warn_count'] ?? 0 }} peringatan aktif. Tunggu konfirmasi lebih kuat sebelum entry.
                    </div>
                </div>
            @endif
        @endif

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <x-panel class="p-4">
                <div class="text-xs text-green-400 uppercase mb-2">Faktor Pendukung</div>
                @forelse($result['supporting_factors'] ?? [] as $factor)
                    <div class="flex gap-2 text-sm text-green-300">
                        <span class="text-green-500 mt-0.5">✓</span><span>{{ $factor }}</span>
                    </div>
                @empty
                    <p class="text-sm text-slate-500">Tidak ada faktor pendukung teridentifikasi.</p>
                @endforelse
            </x-panel>
            <x-panel class="p-4">
                <div class="text-xs text-rose-400 uppercase mb-2">Faktor Risiko</div>
                @forelse($result['risk_factors'] ?? [] as $risk)
                    <div class="flex gap-2 text-sm text-rose-300">
                        <span class="text-rose-500 mt-0.5">⚠</span><span>{{ $risk }}</span>
                    </div>
                @empty
                    <p class="text-sm text-slate-500">Tidak ada faktor risiko teridentifikasi.</p>
                @endforelse
            </x-panel>
        </div>

        @php
            $ind = $result['indicators'] ?? [];
        @endphp
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            @php $macd = $ind['macd'] ?? null; @endphp
            @if($macd)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">MACD</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($macd['trend'] ?? '') === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($macd['trend'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold {{ ($macd['trend'] ?? '') === 'bullish' ? 'text-green-400' : 'text-rose-400' }}">
                        {{ number_format($macd['macd_line'] ?? 0, 2) }}
                    </div>
                    <div class="text-[11px] text-slate-500 mt-1">Signal: {{ number_format($macd['signal_line'] ?? 0, 2) }}</div>
                </div>
            @endif

            @php $bb = $ind['bollinger'] ?? null; @endphp
            @if($bb)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">Bollinger</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($bb['position'] ?? '') === 'above' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($bb['position'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">%B: {{ number_format($bb['percent_b'] ?? 0, 2) }}</div>
                    <div class="text-[11px] text-slate-500 mt-1">Band width: {{ number_format($bb['band_width'] ?? 0, 2) }}</div>
                </div>
            @endif

            @php $stoch = $ind['stochastic'] ?? null; @endphp
            @if($stoch)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">Stochastic</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($stoch['signal'] ?? '') === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($stoch['signal'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">%K: {{ number_format($stoch['percent_k'] ?? 0, 2) }}</div>
                    <div class="text-[11px] text-slate-500 mt-1">%D: {{ number_format($stoch['percent_d'] ?? 0, 2) }}</div>
                </div>
            @endif

            @php $obv = $ind['obv'] ?? null; @endphp
            @if($obv)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">OBV</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($obv['trend'] ?? '') === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($obv['trend'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">{{ number_format($obv['obv'] ?? 0, 2) }}</div>
                </div>
            @endif

            @php $adx = $ind['adx'] ?? null; @endphp
            @if($adx)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">ADX</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($adx['direction'] ?? '') === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($adx['direction'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">ADX: {{ number_format($adx['adx'] ?? 0, 2) }}</div>
                    <div class="text-[11px] text-slate-500 mt-1">+DI {{ number_format($adx['plus_di'] ?? 0, 2) }} / -DI {{ number_format($adx['minus_di'] ?? 0, 2) }}</div>
                </div>
            @endif

            @php $atr = $ind['atr'] ?? null; @endphp
            @if($atr)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">ATR</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($atr['volatility'] ?? '') === 'high' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : (($atr['volatility'] ?? '') === 'low' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-slate-800 text-slate-300 border border-slate-700') }}">
                            {{ strtoupper($atr['volatility'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">{{ number_format($atr['atr'] ?? 0, 2) }}</div>
                    <div class="text-[11px] text-slate-500 mt-1">{{ number_format($atr['atr_percent'] ?? 0, 2) }}%</div>
                </div>
            @endif

            @php $vwap = $ind['vwap'] ?? null; @endphp
            @if($vwap)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">VWAP</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($vwap['position'] ?? '') === 'above' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30' }}">
                            {{ strtoupper($vwap['position'] ?? 'N/A') }}
                        </span>
                    </div>
                    <div class="text-lg font-mono font-bold text-slate-200">{{ number_format($vwap['vwap'] ?? 0, 2) }}</div>
                    <div class="text-[11px] text-slate-500 mt-1">Jarak: {{ number_format($vwap['distance'] ?? 0, 2) }}%</div>
                </div>
            @endif

            @php $candles = $ind['candles'] ?? null; @endphp
            @if($candles)
                <div class="glass-card border border-slate-800 rounded-xl p-4">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 uppercase">Candlestick</span>
                        <span class="px-2 py-0.5 rounded-full text-[11px] {{ ($candles['signal'] ?? '') === 'bullish' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : (($candles['signal'] ?? '') === 'bearish' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-slate-800 text-slate-300 border border-slate-700') }}">
                            {{ strtoupper($candles['signal'] ?? 'N/A') }}
                        </span>
                    </div>
                    @if(($candles['patterns'] ?? []) && count($candles['patterns']) > 0)
                        <div class="space-y-1 text-sm text-slate-200">
                            @foreach($candles['patterns'] as $p)
                                <div class="flex items-center gap-2">
                                    <span class="{{ $p['signal']==='bullish' ? 'text-green-400' : ($p['signal']==='bearish' ? 'text-rose-400' : 'text-slate-400') }}">
                                        {{ $p['signal']==='bullish' ? '▲' : ($p['signal']==='bearish' ? '▼' : '◆') }}
                                    </span>
                                    <span>{{ $p['name'] }}</span>
                                </div>
                            @endforeach
                        </div>
                    @else
                        <div class="text-sm text-slate-400">Tidak ada pola signifikan.</div>
                    @endif
                </div>
            @endif
        </div>

        @php $fund = $result['fundamental'] ?? null; @endphp
        @if($fund)
            <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">PBV</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['pbv'] ? number_format($fund['pbv'],1).'x' : 'N/A' }}</div>
                </div>
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">PER</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['per'] ? number_format($fund['per'],1).'x' : 'N/A' }}</div>
                </div>
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">ROE</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['roe'] !== null ? number_format($fund['roe'],1).'%' : 'N/A' }}</div>
                </div>
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">DER</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['der'] !== null ? number_format($fund['der'],1).'x' : 'N/A' }}</div>
                </div>
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">EPS</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['eps'] !== null ? number_format($fund['eps'],0) : 'N/A' }}</div>
                </div>
                <div class="bg-slate-900 rounded-xl p-3 text-center">
                    <div class="text-[10px] text-slate-500 uppercase">Div Yield</div>
                    <div class="text-lg font-mono font-bold text-slate-100">{{ $fund['dividend_yield'] !== null ? number_format($fund['dividend_yield'],1).'%' : 'N/A' }}</div>
                </div>
            </div>
        @endif

        <div class="space-y-3">
            <h2 class="text-lg font-semibold text-slate-100">Berita Terbaru</h2>
            @forelse($articles->take(10) as $article)
                @php
                    $sentLabel = $article->sentiment_label === 'positive' ? '▲ Positif' : ($article->sentiment_label === 'negative' ? '▼ Negatif' : '◆ Netral');
                    $sentClass = $article->sentiment_label === 'positive' ? 'bg-green-500/10 text-green-400 border-green-500/30' : ($article->sentiment_label === 'negative' ? 'bg-rose-500/10 text-rose-400 border-rose-500/30' : 'bg-slate-800 text-slate-300 border-slate-700');
                @endphp
                <a href="{{ $article->source_url }}" target="_blank" rel="noopener"
                   class="block border border-slate-800 rounded-xl p-4 hover:border-slate-600 transition">
                    <div class="flex justify-between gap-3">
                        <div>
                            <p class="font-medium text-sm leading-snug">{{ $article->title }}</p>
                            <p class="text-[11px] text-slate-500 mt-1">
                                {{ $article->published_at?->format('d M Y H:i') }} • {{ $article->source_provider }}
                            </p>
                        </div>
                        <span class="shrink-0 px-2 py-1 h-fit rounded-full text-[11px] border {{ $sentClass }}">
                            {{ $sentLabel }}
                        </span>
                    </div>
                    <p class="text-[12px] text-slate-400 mt-2 line-clamp-2">
                        {{ \Illuminate\Support\Str::limit($article->summary ?? $article->content_snippet, 150) }}
                    </p>
                </a>
            @empty
                <p class="text-sm text-slate-500">Belum ada berita tersedia.</p>
            @endforelse
        </div>

        <p class="text-xs text-slate-600 text-center mt-6">
            Analisis bersifat indikatif untuk keperluan penelitian akademis. Bukan rekomendasi investasi.
            Data diperbarui: {{ now()->format('d M Y H:i') }} WIB
        </p>
    </div>
</x-app-layout>
