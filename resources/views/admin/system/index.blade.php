<x-app-layout>
    @php
        $currentProvider = $settings['news_provider']->value['value'] ?? config('dashboard.news_provider');
        $currentChartMode = $settings['stock_chart_mode']->value['value'] ?? config('dashboard.stock_chart_mode');
    @endphp
    @if(session('status'))
        <div class="mb-4 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm text-sky-200 break-words">
            {{ session('status') }}
        </div>
    @endif

    <x-panel padding="p-6" class="mb-4">
        <div class="flex items-center justify-between mb-1">
            <h3 class="font-semibold">Jalankan Manual</h3>
            <span class="text-[11px] text-slate-500">sekali klik &mdash; jalan sinkron, tunggu sebentar</span>
        </div>
        <p class="text-xs text-slate-500 mb-4">
            Normalnya semua ini otomatis lewat scheduler. Tombol di sini buat memancing manual
            kalau scheduler kelewat (mis. Mac sempat tidur).
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            @foreach($tasks as $key => $task)
                <form action="{{ route('admin.system.run') }}" method="POST"
                      class="border border-slate-800 rounded-lg p-3 flex flex-col gap-2"
                      onsubmit="this.querySelector('button').disabled=true; this.querySelector('button').innerHTML='Menjalankan…';">
                    @csrf
                    <input type="hidden" name="task" value="{{ $key }}">
                    <div class="text-sm font-medium text-slate-200">{{ $task['label'] }}</div>
                    <div class="text-[11px] text-slate-500 flex-1">{{ $task['note'] }}</div>
                    <button type="submit"
                            class="self-start px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-sky-600 hover:text-white
                                   text-slate-200 text-xs font-semibold transition inline-flex items-center gap-1.5
                                   disabled:opacity-60 disabled:cursor-wait">
                        <x-heroicon-o-play class="w-3.5 h-3.5" /> Jalankan
                    </button>
                </form>
            @endforeach
        </div>
    </x-panel>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <x-panel padding="p-6">
            <h1 class="text-2xl font-bold mb-4">Pengaturan Sistem</h1>
            <form action="{{ route('admin.system.update') }}" method="POST" class="space-y-4">
                @csrf
                <div>
                    <label class="block text-sm text-slate-300">Penyedia Berita</label>
                    <select name="news_provider" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        @foreach(['mock','rss','manual','api'] as $provider)
                            <option value="{{ $provider }}" @selected($currentProvider === $provider)>{{ strtoupper($provider) }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-slate-300">Mode Chart</label>
                    <select name="stock_chart_mode" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2">
                        <option value="tradingview" @selected($currentChartMode === 'tradingview')>TradingView</option>
                        <option value="internal" @selected($currentChartMode === 'internal')>Internal</option>
                    </select>
                </div>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </form>
        </x-panel>

        <x-panel padding="p-6">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-semibold">Log Fetching</h3>
            </div>
            <div class="space-y-2 max-h-80 overflow-auto">
                @foreach($fetchLogs as $log)
                    <div class="border border-slate-800 rounded-lg px-3 py-2">
                        <div class="flex items-center justify-between text-sm">
                            <span class="font-semibold">{{ $log->source_name }}</span>
                            <span class="text-xs text-slate-400">{{ $log->ran_at?->format('d M Y H:i') }}</span>
                        </div>
                        <div class="text-xs text-slate-400">{{ $log->status }} • {{ $log->records_count }} records</div>
                        <div class="text-xs text-slate-500">{{ $log->message }}</div>
                    </div>
                @endforeach
            </div>
        </x-panel>
    </div>
</x-app-layout>
