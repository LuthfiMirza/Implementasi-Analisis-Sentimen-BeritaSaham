<x-app-layout>
    @php
        $currentProvider = $settings['news_provider']->value['value'] ?? config('dashboard.news_provider');
        $currentChartMode = $settings['stock_chart_mode']->value['value'] ?? config('dashboard.stock_chart_mode');
    @endphp
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
