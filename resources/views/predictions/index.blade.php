<x-app-layout>
    <div class="space-y-6">
        <div class="flex items-center justify-between gap-4">
            <div>
                <p class="text-xs uppercase text-slate-400">Predictions</p>
                <h1 class="text-2xl font-bold text-slate-100">Prediksi Saham {{ $stock?->code ?? '-' }}</h1>
            </div>
            <form method="GET">
                <select name="code" onchange="this.form.submit()" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100">
                    @foreach($stocks as $item)
                        <option value="{{ $item->code }}" @selected($stock?->id === $item->id)>{{ $item->code }} — {{ $item->company_name }}</option>
                    @endforeach
                </select>
            </form>
        </div>

        @if($prediction)
            @php
                $direction = strtolower($prediction['predicted_direction'] ?? 'flat');
                $badge = match ($direction) {
                    'up' => 'bg-green-500/20 text-green-300',
                    'down' => 'bg-rose-500/20 text-rose-300',
                    default => 'bg-slate-700 text-slate-200',
                };
            @endphp
            <x-panel class="p-6 space-y-5">
                <div class="flex flex-wrap items-center gap-3">
                    <span class="px-3 py-1 rounded-full text-sm font-semibold {{ $badge }}">
                        {{ strtoupper($direction) }}
                    </span>
                    <span class="px-3 py-1 rounded-full text-xs bg-sky-500/15 text-sky-300">
                        {{ $predictionSource }}
                    </span>
                </div>

                <div>
                    <div class="text-xs uppercase text-slate-400">Probability</div>
                    <div class="text-4xl font-bold text-slate-100">{{ number_format(((float) ($prediction['probability'] ?? 0)) * 100, 1) }}%</div>
                </div>

                <div>
                    <div class="text-xs uppercase text-slate-400">Basis</div>
                    <p class="text-sm text-slate-300 mt-1">{{ $prediction['basis'] ?? '-' }}</p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <div class="rounded-lg border border-slate-800 p-3">
                        <div class="text-green-300 font-semibold">Bullish</div>
                        <p class="text-slate-400 mt-1">{{ $prediction['scenario_bullish'] ?? '-' }}</p>
                    </div>
                    <div class="rounded-lg border border-slate-800 p-3">
                        <div class="text-slate-200 font-semibold">Neutral</div>
                        <p class="text-slate-400 mt-1">{{ $prediction['scenario_neutral'] ?? '-' }}</p>
                    </div>
                    <div class="rounded-lg border border-slate-800 p-3">
                        <div class="text-rose-300 font-semibold">Bearish</div>
                        <p class="text-slate-400 mt-1">{{ $prediction['scenario_bearish'] ?? '-' }}</p>
                    </div>
                </div>
            </x-panel>
        @else
            <x-panel class="p-6 text-center text-slate-300">
                Prediction unavailable.
            </x-panel>
        @endif
    </div>
</x-app-layout>
