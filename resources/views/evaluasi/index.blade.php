<x-app-layout>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div class="flex items-center justify-between gap-3">
            <div>
                <p class="text-xs uppercase text-slate-400">Analisis Decision Support System</p>
                <h1 class="text-2xl font-bold text-slate-100">Evaluasi Model & Laporan Prediksi</h1>
                <p class="text-sm text-slate-400">Tanggal: {{ now()->format('d M Y') }}</p>
                <p class="text-xs text-slate-500 mt-1">Diperbarui: {{ now()->format('d M Y H:i') }} WIB</p>
                <div class="flex items-center gap-3">
                    <a href="{{ route('evaluasi.sentimen') }}" class="text-xs text-sky-400 hover:underline">Audit Sentimen →</a>
                    <a href="{{ route('backtest.all') }}" class="text-xs text-amber-400 hover:underline">Backtest DSS →</a>
                </div>
            </div>
            <span class="px-3 py-1 rounded-full text-sm bg-slate-800 text-slate-200 border border-slate-700">
                {{ $summary['total_stocks'] ?? 0 }} Saham Aktif
            </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <x-panel class="p-4 space-y-2">
                <div class="text-xs uppercase text-slate-400">Distribusi Prediksi</div>
                <div class="space-y-2 mt-3">
                    <div class="flex items-center gap-2">
                        <span class="text-green-400 font-bold w-4">▲</span>
                        <span class="text-sm text-slate-300">UP</span>
                        <div class="flex-1 bg-slate-800 rounded-full h-1.5">
                            <div class="h-1.5 rounded-full bg-green-500" style="width: {{ ($summary['total_stocks'] ?? 0) > 0 ? (($summary['pred_up'] ?? 0)/$summary['total_stocks']*100) : 0 }}%"></div>
                        </div>
                        <span class="text-green-400 font-bold text-sm w-4">{{ $summary['pred_up'] ?? 0 }}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-slate-400 font-bold w-4">→</span>
                        <span class="text-sm text-slate-300">FLAT</span>
                        <div class="flex-1 bg-slate-800 rounded-full h-1.5">
                            <div class="h-1.5 rounded-full bg-slate-500" style="width: {{ ($summary['total_stocks'] ?? 0) > 0 ? (($summary['pred_flat'] ?? 0)/$summary['total_stocks']*100) : 0 }}%"></div>
                        </div>
                        <span class="text-slate-400 font-bold text-sm w-4">{{ $summary['pred_flat'] ?? 0 }}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-rose-400 font-bold w-4">▼</span>
                        <span class="text-sm text-slate-300">DOWN</span>
                        <div class="flex-1 bg-slate-800 rounded-full h-1.5">
                            <div class="h-1.5 rounded-full bg-rose-500" style="width: {{ ($summary['total_stocks'] ?? 0) > 0 ? (($summary['pred_down'] ?? 0)/$summary['total_stocks']*100) : 0 }}%"></div>
                        </div>
                        <span class="text-rose-400 font-bold text-sm w-4">{{ $summary['pred_down'] ?? 0 }}</span>
                    </div>
                </div>
            </x-panel>

            <x-panel class="p-4 space-y-2">
                <div class="text-xs uppercase text-slate-400">Rata-rata Model</div>
                <div class="text-sm flex items-center justify-between">
                    <span>Avg Score</span><span class="font-semibold">{{ $summary['avg_score'] ?? 0 }}/100</span>
                </div>
                <div class="text-sm flex items-center justify-between">
                    <span>Avg Confidence</span><span class="font-semibold">{{ $summary['avg_confidence'] ?? 0 }}</span>
                </div>
            </x-panel>

            <x-panel class="p-4 space-y-2">
                <div class="text-xs uppercase text-slate-400">Coverage Berita</div>
                <div class="text-sm flex items-center justify-between">
                    <span>High (≥10)</span><span class="font-semibold">{{ $summary['high_coverage'] ?? 0 }}</span>
                </div>
                <div class="text-sm flex items-center justify-between">
                    <span>Low (&lt;5)</span><span class="font-semibold">{{ $summary['low_coverage'] ?? 0 }}</span>
                </div>
                <div class="text-sm flex items-center justify-between">
                    <span>Avg berita/saham</span><span class="font-semibold">{{ $summary['avg_news'] ?? 0 }}</span>
                </div>
            </x-panel>

            <x-panel class="p-4 space-y-1 text-sm text-slate-300">
                <div class="text-xs uppercase text-slate-400">Metodologi Bobot</div>
                <div>Sentimen 20% • Trend 22% • Momentum 18%</div>
                <div>Volume/OBV 13% • Volatilitas 12% • Fundamental 15%</div>
            </x-panel>

            @if(($summary['ml_total'] ?? 0) > 0)
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Audit Sentimen</div>
                    <div class="text-lg font-bold text-purple-400">{{ $summary['ml_agree_rate'] }}% agreement</div>
                    <div class="text-sm text-slate-400">{{ $summary['ml_total'] }} artikel dianalisis ML</div>
                </x-panel>
            @endif
        </div>

        <x-panel class="p-0 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm text-slate-200">
                    <thead class="bg-slate-900 text-xs uppercase text-slate-400 sticky top-0">
                        <tr>
                            <th class="px-4 py-3 text-left">Saham</th>
                            <th class="px-4 py-3 text-left">Score</th>
                            <th class="px-4 py-3 text-left">Status</th>
                            <th class="px-4 py-3 text-left">Prediksi</th>
                            <th class="px-4 py-3 text-left">Confidence</th>
                            <th class="px-4 py-3 text-left">Sentimen Avg</th>
                            <th class="px-4 py-3 text-left">Berita</th>
                            <th class="px-4 py-3 text-left">Indikator</th>
                            <th class="px-4 py-3 text-left">Fundamental</th>
                            <th class="px-4 py-3 text-right">Detail</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        @foreach($results as $r)
                            <tr class="hover:bg-slate-800/50 transition cursor-pointer" onclick="window.location='{{ route('evaluasi.show', $r['code']) }}'">
                                <td class="px-4 py-3">
                                    <div class="font-semibold">{{ $r['code'] }}</div>
                                    <div class="text-xs text-slate-400">{{ $r['name'] }}</div>
                                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">{{ $r['sector'] }}</span>
                                </td>
                                <td class="px-4 py-3">
                                    <div class="flex items-center gap-2">
                                        <div class="w-16 bg-slate-800 rounded-full h-1.5">
                                            <div class="h-1.5 rounded-full {{ $r['score'] >= 60 ? 'bg-green-500' : ($r['score'] >= 45 ? 'bg-amber-500' : 'bg-rose-500') }}"
                                                 style="width: {{ $r['score'] }}%"></div>
                                        </div>
                                        <span class="font-mono text-sm {{ $r['score'] >= 60 ? 'text-green-400' : ($r['score'] >= 45 ? 'text-amber-400' : 'text-rose-400') }}">
                                            {{ $r['score'] }}
                                        </span>
                                    </div>
                                </td>
                                <td class="px-4 py-3">
                                    <span class="inline-flex items-center max-w-[140px] text-xs px-2.5 py-1 rounded-full border border-slate-700 text-slate-200 bg-slate-900/60 whitespace-nowrap overflow-hidden text-ellipsis">
                                        {{ $r['status'] }}
                                    </span>
                                </td>
                                <td class="px-4 py-3">
                                    @if($r['prediction'] === 'up')
                                        <span class="flex items-center gap-1 text-green-400 font-medium">▲ UP</span>
                                    @elseif($r['prediction'] === 'down')
                                        <span class="flex items-center gap-1 text-rose-400 font-medium">▼ DOWN</span>
                                    @else
                                        <span class="flex items-center gap-1 text-slate-400">→ FLAT</span>
                                    @endif
                                </td>
                                <td class="px-4 py-3">
                                    <div class="w-24 bg-slate-800 rounded-full h-2">
                                        <div class="h-2 rounded-full bg-sky-500" style="width: {{ ($r['confidence'] ?? 0) * 100 }}%"></div>
                                    </div>
                                    <span class="text-xs text-slate-300">{{ round(($r['confidence'] ?? 0)*100,1) }}%</span>
                                </td>
                                <td class="px-4 py-3">
                                    <span class="text-sm {{ $r['sentiment_avg'] > 0 ? 'text-green-400' : ($r['sentiment_avg'] < 0 ? 'text-rose-400' : 'text-slate-300') }}">
                                        {{ $r['sentiment_avg'] }}
                                    </span>
                                </td>
                                <td class="px-4 py-3 align-top">
                                    @php
                                        $newsColor = $r['news_count'] >= 10 ? 'bg-green-500/20 text-green-300' : ($r['news_count'] >=5 ? 'bg-amber-500/20 text-amber-300' : 'bg-rose-500/20 text-rose-300');
                                    @endphp
                                    <div class="flex flex-col gap-1">
                                        <span class="px-2 py-0.5 rounded-full text-xs {{ $newsColor }}">{{ $r['news_count'] }} berita</span>
                                        <span class="text-[10px] text-slate-500">Candles: {{ $r['candle_count'] }}</span>
                                    </div>
                                </td>
                                <td class="px-4 py-3 text-[11px] text-slate-300 align-top">
                                    <div class="flex flex-wrap gap-2 items-center min-w-[220px]">
                                        @if($r['macd_trend'])<span class="px-2 py-0.5 rounded-full border border-slate-700 bg-slate-800/60">MACD: {{ $r['macd_trend'] }}</span>@endif
                                        @if($r['bb_position'])<span class="px-2 py-0.5 rounded-full border border-slate-700 bg-slate-800/60">BB: {{ $r['bb_position'] }}</span>@endif
                                        @if($r['stoch_signal'])<span class="px-2 py-0.5 rounded-full border border-slate-700 bg-slate-800/60">Stoch: {{ $r['stoch_signal'] }}</span>@endif
                                        @if($r['obv_trend'])<span class="px-2 py-0.5 rounded-full border border-slate-700 bg-slate-800/60">OBV: {{ $r['obv_trend'] }}</span>@endif
                                        @if($r['adx_strength'])<span class="px-2 py-0.5 rounded-full border border-slate-700 bg-slate-800/60">ADX: {{ $r['adx_strength'] }}</span>@endif
                                        @if($r['rsi'])
                                            <span class="px-2 py-0.5 rounded-full text-[10px] border border-slate-700 bg-slate-800/60 text-slate-300">
                                                RSI: {{ number_format($r['rsi'], 1) }}
                                            </span>
                                        @endif
                                    </div>
                                </td>
                                <td class="px-4 py-3 text-sm text-slate-300">
                                    @php
                                        $fundamentalSnapshotDate = $r['fundamentals_updated_at']
                                            ? \Illuminate\Support\Carbon::parse($r['fundamentals_updated_at'])->format('d M Y')
                                            : 'tidak diketahui';
                                    @endphp
                                    <div class="mb-2 inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                                        Data fundamental: snapshot per {{ $fundamentalSnapshotDate }} — belum real-time
                                    </div>
                                    <div>PBV: {{ $r['pbv'] ?? 'N/A' }}</div>
                                    <div>ROE: {{ $r['roe'] ?? 'N/A' }}</div>
                                    <div class="mt-1 text-[10px] text-slate-500">
                                        Untuk data fundamental terkini, verifikasi ke IDX, RTI Business, atau laporan keuangan perusahaan.
                                    </div>
                                </td>
                                <td class="px-4 py-3 text-right">
                                    <a href="{{ route('evaluasi.show', $r['code']) }}" class="text-xs text-sky-400 hover:underline">Detail →</a>
                                </td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
        </x-panel>

        <div class="space-y-4">
            @foreach($results as $r)
                <div class="glass-card border border-slate-800/80 rounded-2xl p-5">
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <div class="font-semibold text-slate-100">{{ $r['code'] }} — {{ $r['name'] }}</div>
                            <div class="text-xs text-slate-500">{{ $r['sector'] }}</div>
                        </div>
                        <div class="text-sm text-slate-300">
                            Prediksi: <span class="font-semibold {{ $r['prediction']==='up' ? 'text-green-400' : ($r['prediction']==='down' ? 'text-rose-400' : 'text-slate-300') }}">
                                {{ strtoupper($r['prediction'] ?? 'N/A') }}
                            </span>
                            ({{ round(($r['confidence'] ?? 0)*100,1) }}%)
                        </div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                        <div class="bg-green-500/10 border border-green-500/20 rounded-xl p-3">
                            <div class="text-xs text-green-400 mb-1">Skenario Bullish</div>
                            <p class="text-sm text-slate-300">{{ $r['scenario_bull'] }}</p>
                        </div>
                        <div class="bg-slate-800 rounded-xl p-3">
                            <div class="text-xs text-slate-400 mb-1">Skenario Netral</div>
                            <p class="text-sm text-slate-300">{{ $r['scenario_flat'] }}</p>
                        </div>
                        <div class="bg-rose-500/10 border border-rose-500/20 rounded-xl p-3">
                            <div class="text-xs text-rose-400 mb-1">Skenario Bearish</div>
                            <p class="text-sm text-slate-300">{{ $r['scenario_bear'] }}</p>
                        </div>
                    </div>
                </div>
            @endforeach
        </div>

        <div class="text-xs text-slate-500 text-center">
            Model bersifat indikatif untuk keperluan penelitian akademis. Bukan rekomendasi investasi. Data diperbarui: {{ now()->format('d M Y H:i') }} WIB
        </div>
    </div>
</x-app-layout>
