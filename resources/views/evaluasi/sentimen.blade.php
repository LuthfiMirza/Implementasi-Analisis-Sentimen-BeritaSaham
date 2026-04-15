<x-app-layout>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div class="flex items-center justify-between gap-3">
            <div>
                <p class="text-xs uppercase text-slate-400">Evaluasi Sentimen — ML vs Rule-Based</p>
                <h1 class="text-2xl font-bold text-slate-100">IndoBERT vs Leksikon</h1>
                <p class="text-xs text-slate-500 mt-1">Data per {{ now()->format('d M Y') }}</p>
            </div>
            <div class="flex items-center gap-3">
                <span class="px-3 py-1 rounded-full text-sm bg-slate-800 text-slate-200 border border-slate-700">
                    {{ $total ?? 0 }} artikel dianalisis
                </span>
                <a href="{{ route('evaluation.index') }}" class="text-xs text-sky-400 hover:underline">Evaluasi News →</a>
            </div>
        </div>

        @if(!empty($empty))
            <x-panel class="p-6 text-center text-slate-300">
                Belum ada artikel dengan label ML + Rule. Jalankan <code class="bg-slate-800 px-2 py-1 rounded border border-slate-700">php artisan sentiment:reanalyze --limit=20</code> setelah konfigurasi IndoBERT aktif.
            </x-panel>
        @else
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Total Artikel</div>
                    <div class="text-3xl font-bold text-slate-100">{{ $total }}</div>
                    <div class="text-sm text-slate-400">Dengan label ML & Rule</div>
                </x-panel>
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Agreement Rate</div>
                    @php
                        $agreeColor = $agreeRate > 70 ? 'text-green-400' : ($agreeRate >= 50 ? 'text-amber-400' : 'text-rose-400');
                    @endphp
                    <div class="text-3xl font-bold {{ $agreeColor }}">{{ $agreeRate }}%</div>
                    <div class="text-sm text-slate-400">Agree {{ $agree }} | Disagree {{ $disagree }}</div>
                </x-panel>
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Disagree</div>
                    <div class="text-3xl font-bold text-amber-400">{{ $disagree }}</div>
                    <div class="text-sm text-slate-400">Artikel dengan label berbeda</div>
                </x-panel>
                <x-panel class="p-4 space-y-2">
                    <div class="text-xs uppercase text-slate-400">Avg ML Confidence</div>
                    <div class="text-3xl font-bold text-sky-400">{{ round($avgMlConfidence * 100, 1) }}%</div>
                    <div class="text-sm text-slate-400">Rata-rata probabilitas tertinggi</div>
                </x-panel>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <x-panel class="p-4 space-y-3">
                    <div class="flex items-center justify-between">
                        <div class="text-sm font-semibold text-slate-200">Distribusi IndoBERT</div>
                        <div class="text-xs text-slate-500">ML</div>
                    </div>
                    @php $mlTotal = max(1, array_sum($mlDist)); @endphp
                    @foreach($mlDist as $label => $count)
                        @php
                            $percent = round($count / $mlTotal * 100, 1);
                            $color = $label === 'positive' ? 'bg-green-500' : ($label === 'negative' ? 'bg-rose-500' : 'bg-slate-500');
                        @endphp
                        <div class="space-y-1">
                            <div class="flex items-center justify-between text-sm text-slate-300">
                                <span class="capitalize">{{ $label }}</span>
                                <span>{{ $count }} ({{ $percent }}%)</span>
                            </div>
                            <div class="w-full bg-slate-800 rounded-full h-2">
                                <div class="h-2 rounded-full {{ $color }}" style="width: {{ $percent }}%"></div>
                            </div>
                        </div>
                    @endforeach
                </x-panel>

                <x-panel class="p-4 space-y-3">
                    <div class="flex items-center justify-between">
                        <div class="text-sm font-semibold text-slate-200">Distribusi Rule-Based</div>
                        <div class="text-xs text-slate-500">Lexicon</div>
                    </div>
                    @php $ruleTotal = max(1, array_sum($ruleDist)); @endphp
                    @foreach($ruleDist as $label => $count)
                        @php
                            $percent = round($count / $ruleTotal * 100, 1);
                            $color = $label === 'positive' ? 'bg-green-500' : ($label === 'negative' ? 'bg-rose-500' : 'bg-slate-500');
                        @endphp
                        <div class="space-y-1">
                            <div class="flex items-center justify-between text-sm text-slate-300">
                                <span class="capitalize">{{ $label }}</span>
                                <span>{{ $count }} ({{ $percent }}%)</span>
                            </div>
                            <div class="w-full bg-slate-800 rounded-full h-2">
                                <div class="h-2 rounded-full {{ $color }}" style="width: {{ $percent }}%"></div>
                            </div>
                        </div>
                    @endforeach
                </x-panel>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <x-panel class="p-4">
                    <div class="text-sm font-semibold text-slate-200 mb-3">Confusion Matrix (Rule → ML)</div>
                    <div class="overflow-x-auto">
                        <table class="min-w-full text-sm text-slate-200">
                            <thead>
                                <tr>
                                    <th class="px-2 py-2 text-left text-xs text-slate-400">Rule \\ ML</th>
                                    @foreach($labels as $ml)
                                        <th class="px-2 py-2 text-center capitalize text-xs text-slate-400">{{ $ml }}</th>
                                    @endforeach
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800">
                                @foreach($labels as $rule)
                                    <tr>
                                        <td class="px-2 py-2 text-xs capitalize text-slate-400">{{ $rule }}</td>
                                        @foreach($labels as $ml)
                                            @php
                                                $value = $matrix[$rule][$ml] ?? 0;
                                                $class = $rule === $ml ? 'bg-green-500/20 text-green-200' : 'bg-amber-500/10 text-amber-200';
                                            @endphp
                                            <td class="px-2 py-2 text-center rounded {{ $class }}">{{ $value }}</td>
                                        @endforeach
                                    </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                </x-panel>

                <x-panel class="p-4">
                    <div class="text-sm font-semibold text-slate-200 mb-3">Per-Class Metrics (Rule as predicted, ML as truth)</div>
                    <table class="min-w-full text-sm text-slate-200">
                        <thead>
                            <tr class="text-xs text-slate-400">
                                <th class="px-2 py-2 text-left">Label</th>
                                <th class="px-2 py-2 text-left">Precision</th>
                                <th class="px-2 py-2 text-left">Recall</th>
                                <th class="px-2 py-2 text-left">F1</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            @foreach($metrics as $label => $m)
                                <tr>
                                    <td class="px-2 py-2 capitalize">{{ $label }}</td>
                                    <td class="px-2 py-2">{{ number_format($m['precision'], 3) }}</td>
                                    <td class="px-2 py-2">{{ number_format($m['recall'], 3) }}</td>
                                    <td class="px-2 py-2">{{ number_format($m['f1'], 3) }}</td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </x-panel>

                <x-panel class="p-4">
                    <div class="text-sm font-semibold text-slate-200 mb-3">Per-Stock Agreement</div>
                    <div class="space-y-3 max-h-72 overflow-auto pr-1">
                        @foreach($perStock as $item)
                            <div class="p-3 rounded-xl bg-slate-800/60 border border-slate-700">
                                <div class="flex items-center justify-between text-sm text-slate-200">
                                    <span class="font-semibold">{{ $item['code'] }}</span>
                                    <span class="text-xs text-slate-400">{{ $item['total'] }} artikel</span>
                                </div>
                                <div class="mt-1 flex items-center gap-2">
                                    <div class="flex-1 bg-slate-900 rounded-full h-2">
                                        <div class="h-2 rounded-full bg-sky-500" style="width: {{ $item['agree_rate'] }}%"></div>
                                    </div>
                                    <span class="text-xs text-slate-300">{{ $item['agree_rate'] }}%</span>
                                </div>
                                <div class="mt-2 text-[11px] text-slate-400 flex gap-2">
                                    <span class="text-green-300">+{{ $item['ml_pos'] }}</span>
                                    <span class="text-slate-300">0{{ $item['ml_neu'] }}</span>
                                    <span class="text-rose-300">-{{ $item['ml_neg'] }}</span>
                                </div>
                            </div>
                        @endforeach
                    </div>
                </x-panel>
            </div>

            <x-panel class="p-4 space-y-3">
                <div class="flex items-center justify-between">
                    <div>
                        <div class="text-sm font-semibold text-slate-200">Contoh Disagreement (Top 10)</div>
                        <div class="text-xs text-slate-500">Urut confidence ML tertinggi</div>
                    </div>
                    <a href="{{ route('news.index') }}" class="text-xs text-sky-400 hover:underline">Lihat Artikel →</a>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                    @forelse($disagreements as $art)
                        <div class="p-3 rounded-xl border border-amber-500/30 bg-amber-500/5">
                            <div class="text-sm font-semibold text-slate-100 mb-1">{{ $art->title }}</div>
                            <div class="flex items-center gap-2 text-xs">
                                <span class="px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-200">ML: {{ $art->ml_sentiment_label }} ({{ round(($art->ml_confidence ?? 0) * 100, 1) }}%)</span>
                                <span class="px-2 py-0.5 rounded-full bg-slate-700 text-slate-200">Rule: {{ $art->rule_sentiment_label }}</span>
                            </div>
                            <p class="text-xs text-slate-400 mt-2 line-clamp-2">{{ $art->summary ?? $art->content_snippet }}</p>
                        </div>
                    @empty
                        <p class="text-slate-400 text-sm">Semua artikel saat ini sedang agree.</p>
                    @endforelse
                </div>
            </x-panel>

            <div class="text-xs text-slate-500 text-center">
                Model ML: w11wo/indonesian-roberta-base-sentiment-classifier • Rule-based: leksikon finansial ID • {{ now()->format('d M Y H:i') }}
            </div>
        @endif
    </div>
</x-app-layout>
