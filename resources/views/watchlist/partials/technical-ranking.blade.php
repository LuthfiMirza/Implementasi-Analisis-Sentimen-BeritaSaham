@php
    $ranking = $technicalRanking ?? ['available' => false, 'ranked' => []];
    $entries = collect($ranking['ranked'] ?? []);
    $excludedTickers = collect($ranking['excluded_tickers'] ?? [])->filter()->values();
    $eligibleTickers = collect($ranking['eligible_tickers'] ?? [])->filter()->values();
@endphp

<x-panel padding="p-5" class="mb-5">
    <div class="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
            <p class="text-xs uppercase text-slate-400">Technical Ranking</p>
            <h2 class="text-xl font-bold">Relative Strength Ranking (5-Day Horizon)</h2>
            <p class="text-sm text-slate-400">
                Panel ini menampilkan relative technical strength dan momentum rank lintas ticker watchlist sebagai indikator probabilistik.
            </p>
        </div>
        <div class="text-xs text-slate-400">
            <div>Model: {{ $ranking['model_version'] ?? 'v5_ranking' }}</div>
            <div>Reference date: {{ $ranking['reference_date'] ?? '-' }}</div>
            @if(!empty($ranking['snapshot_date']))
                <div>Snapshot date: {{ $ranking['snapshot_date'] }}</div>
            @endif
        </div>
    </div>

    @if($excludedTickers->isNotEmpty())
        <div class="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            Ranking ini hanya memakai ticker yang eligible: {{ $eligibleTickers->implode(', ') ?: '-' }}.
            Ticker tanpa coverage feature dikeluarkan sementara: {{ $excludedTickers->implode(', ') }}.
        </div>
    @endif

    @if(($ranking['available'] ?? false) && $entries->isNotEmpty())
        <div class="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
            @foreach($entries as $entry)
                @php
                    $score = (float) ($entry['score'] ?? 0);
                    $signal = (string) ($entry['signal'] ?? 'neutral');
                    $scoreWidth = max(4, min(100, round($score * 100, 1)));
                    $signalTone = match ($signal) {
                        'strong_candidate' => [
                            'label' => 'Strong candidate',
                            'chip' => 'bg-green-500/15 text-green-300 border border-green-500/30',
                            'bar' => 'bg-green-500',
                        ],
                        'candidate' => [
                            'label' => 'Candidate',
                            'chip' => 'bg-sky-500/15 text-sky-300 border border-sky-500/30',
                            'bar' => 'bg-sky-400',
                        ],
                        'avoid' => [
                            'label' => 'Avoid',
                            'chip' => 'bg-rose-500/15 text-rose-300 border border-rose-500/30',
                            'bar' => 'bg-rose-500',
                        ],
                        default => [
                            'label' => 'Neutral',
                            'chip' => 'bg-slate-800 text-slate-300 border border-slate-700',
                            'bar' => 'bg-slate-400',
                        ],
                    };
                @endphp
                <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <div class="text-xs uppercase text-slate-500">Momentum rank</div>
                            <div class="flex items-center gap-3 mt-1">
                                <span class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-700 bg-slate-950 text-sm font-semibold">
                                    {{ $entry['rank'] }}
                                </span>
                                <div>
                                    <div class="text-lg font-semibold">{{ $entry['ticker'] }}</div>
                                    <div class="text-xs text-slate-400">Kandidat teknikal relatif terhadap watchlist saat ini</div>
                                </div>
                            </div>
                        </div>
                        <span class="text-[11px] px-2 py-1 rounded-full {{ $signalTone['chip'] }}">{{ $signalTone['label'] }}</span>
                    </div>

                    <div class="mt-4">
                        <div class="flex items-center justify-between text-xs text-slate-400 mb-1">
                            <span>Relative technical strength score</span>
                            <span>{{ number_format($score, 2) }}</span>
                        </div>
                        <div class="h-2 rounded-full bg-slate-800 overflow-hidden">
                            <div class="h-full {{ $signalTone['bar'] }}" style="width: {{ $scoreWidth }}%"></div>
                        </div>
                    </div>
                </div>
            @endforeach
        </div>
    @else
        <div class="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-slate-400">
            {{ $ranking['message'] ?? 'Relative technical strength ranking belum tersedia untuk watchlist ini.' }}
        </div>
    @endif

    <div class="mt-4 rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-xs text-slate-400">
        Model ini bersifat indikatif berbasis analisis teknikal historis. Bukan rekomendasi investasi. Precision top-3: 52.65%, selalu gunakan manajemen risiko.
    </div>
</x-panel>
