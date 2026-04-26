<x-app-layout>
    <x-panel padding="p-6">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
            <div>
                <p class="text-xs uppercase text-slate-400">Watchlist</p>
                <h1 class="text-2xl font-bold">Pantau Saham Favorit</h1>
                <p class="text-sm text-slate-400">Tambah atau hapus saham dari watchlist pribadi Anda.</p>
            </div>
            <div class="flex flex-col gap-2">
                <form method="GET" class="flex items-center gap-2">
                    <input type="text" name="q" value="{{ $search }}" placeholder="Cari watchlist..." class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                    <button class="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm">Cari</button>
                </form>
                <form method="POST" action="{{ route('watchlist.store') }}" class="flex items-center gap-3">
                    @csrf
                    <select name="stock_id" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm">
                        @foreach($stocks as $stock)
                            <option value="{{ $stock->id }}">{{ $stock->code }} - {{ $stock->company_name }}</option>
                        @endforeach
                    </select>
                    <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Tambah</button>
                </form>
            </div>
        </div>

        @if (session('status'))
            <div class="mb-4 text-sm text-green-400">{{ session('status') }}</div>
        @endif

        @include('watchlist.partials.technical-ranking', ['technicalRanking' => $technicalRanking ?? []])

        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            @forelse($items as $item)
                @php
                    $stock = $item['stock'];
                    $latest = $item['latest'];
                    $decision = $item['decision'];
                    $spark = $item['sparkline'];
                    $statusColor = match($decision['status']) {
                        'Bullish Support' => 'bg-green-500/15 text-green-300 border border-green-500/30',
                        'Warning' => 'bg-rose-500/15 text-rose-300 border border-rose-500/30',
                        default => 'bg-amber-500/15 text-amber-200 border border-amber-500/30',
                    };
                @endphp
                <div class="border border-slate-800 rounded-xl p-4 bg-slate-900/50 hover:border-slate-700 transition">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <div class="font-bold text-lg">{{ $stock->code }}</div>
                            <div class="text-xs text-slate-400">{{ \Illuminate\Support\Str::limit($stock->company_name, 48) }}</div>
                        </div>
                        <span class="text-[11px] px-2 py-1 rounded-full {{ $statusColor }}">{{ $decision['status'] }}</span>
                    </div>
                    <div class="flex items-center justify-between mt-3">
                        <div>
                            <div class="text-2xl font-semibold">{{ $latest?->close ? number_format($latest->close, 2) : '-' }}</div>
                            @if($latest && $latest->open)
                                @php $chg = (($latest->close - $latest->open)/$latest->open)*100; @endphp
                                <div class="text-sm {{ $chg >= 0 ? 'text-green-400' : 'text-rose-400' }}">{{ number_format($chg, 2) }}%</div>
                            @endif
                        </div>
                        <div class="flex items-end gap-1 h-12">
                            @forelse($spark as $val)
                                @php
                                    $height = max(6, min(36, (abs($val) * 30) + 6));
                                    $color = $val >= 0 ? 'bg-green-400' : 'bg-rose-400';
                                @endphp
                                <div class="w-1.5 rounded-full {{ $color }}" style="height: {{ $height }}px"></div>
                            @empty
                                <span class="text-xs text-slate-400">-</span>
                            @endforelse
                        </div>
                    </div>
                    <div class="flex items-center justify-between text-xs text-slate-400 mt-2">
                        <span>Sentimen: {{ $decision['weighted_sentiment'] ?? $decision['sentiment_average'] }}</span>
                        <span>Conf: {{ $decision['confidence'] }}</span>
                    </div>
                    @if($item['negative_alert'])
                        <div class="mt-3 text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
                            Lonjakan berita negatif ({{ $item['negative_alert_count'] }}) dalam 24 jam.
                        </div>
                    @endif
                    <div class="flex items-center justify-between mt-3 text-sm">
                        <a href="{{ route('analytics.index', ['code' => $stock->code]) }}" class="text-sky-400 hover:text-sky-300">Buka analytics</a>
                        <form method="POST" action="{{ route('watchlist.destroy', $stock) }}" class="inline">
                            @csrf
                            @method('DELETE')
                            <button class="text-rose-400 hover:text-rose-300 text-xs">Hapus</button>
                        </form>
                    </div>
                </div>
            @empty
                <p class="text-sm text-slate-400">Watchlist kosong. Tambahkan saham untuk mulai memantau.</p>
            @endforelse
        </div>
    </x-panel>
</x-app-layout>
