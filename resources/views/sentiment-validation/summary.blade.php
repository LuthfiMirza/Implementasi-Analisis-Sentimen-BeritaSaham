<x-app-layout>
    <div class="max-w-3xl mx-auto space-y-4">
        <x-panel padding="p-6">
            <p class="text-xs uppercase text-slate-400">Validasi Kualitas Sentimen (Gap 2)</p>
            <h1 class="text-2xl font-bold text-slate-100">Ringkasan Hasil Validasi Manual</h1>
            <p class="text-sm text-slate-400 mt-2">
                Berdasarkan {{ $total }} artikel yang sudah dilabel manual (dari kasus ML vs rule-based disagreement).
            </p>
        </x-panel>

        @if($total === 0)
            <x-panel padding="p-6" class="text-center text-slate-300">
                Belum ada artikel yang dilabel. <a href="{{ route('sentiment-validation.index') }}" class="text-sky-400 hover:underline">Mulai label sekarang →</a>
            </x-panel>
        @else
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <x-panel padding="p-6" class="text-center">
                    <p class="text-xs uppercase text-slate-400">ML Agreement Rate</p>
                    <p class="text-4xl font-bold {{ $mlAgreeRate >= 60 ? 'text-green-300' : 'text-amber-300' }} mt-2">{{ $mlAgreeRate }}%</p>
                    <p class="text-xs text-slate-500 mt-1">ML cocok dengan label manual kamu</p>
                </x-panel>
                <x-panel padding="p-6" class="text-center">
                    <p class="text-xs uppercase text-slate-400">Rule-based Agreement Rate</p>
                    <p class="text-4xl font-bold {{ $ruleAgreeRate >= 60 ? 'text-green-300' : 'text-amber-300' }} mt-2">{{ $ruleAgreeRate }}%</p>
                    <p class="text-xs text-slate-500 mt-1">Rule-based cocok dengan label manual kamu</p>
                </x-panel>
            </div>

            <x-panel padding="p-6" class="text-sm">
                @if($mlAgreeRate > $ruleAgreeRate)
                    <p class="text-slate-200">
                        <strong class="text-green-300">ML lebih akurat</strong> dibanding rule-based pada sample ini
                        (+{{ number_format($mlAgreeRate - $ruleAgreeRate, 1) }} poin). Ini mendukung keputusan sistem
                        saat ini yang selalu memenangkan ML kalau keduanya beda pendapat.
                    </p>
                @elseif($ruleAgreeRate > $mlAgreeRate)
                    <p class="text-slate-200">
                        <strong class="text-rose-300">Rule-based ternyata lebih akurat</strong> dibanding ML pada sample ini
                        (+{{ number_format($ruleAgreeRate - $mlAgreeRate, 1) }} poin). Ini bertentangan dengan aturan
                        sistem saat ini yang selalu memenangkan ML — pertimbangkan ubah tie-break rule atau audit
                        model ML lebih lanjut.
                    </p>
                @else
                    <p class="text-slate-200">ML dan rule-based sama akuratnya pada sample ini.</p>
                @endif
            </x-panel>

            <x-panel padding="p-6">
                <h2 class="text-sm font-semibold text-slate-100 mb-3">Confusion Matrix: ML vs Manual</h2>
                <table class="w-full text-xs text-slate-300">
                    <thead class="text-slate-500 uppercase">
                        <tr><th class="text-left py-1">ML bilang →</th><th>manual: positive</th><th>manual: neutral</th><th>manual: negative</th></tr>
                    </thead>
                    <tbody>
                        @foreach(['positive', 'neutral', 'negative'] as $mlLabel)
                            <tr class="border-t border-slate-800">
                                <td class="py-1 font-semibold">{{ $mlLabel }}</td>
                                @foreach(['positive', 'neutral', 'negative'] as $manualLabel)
                                    <td class="text-center">{{ $confusionMl[$mlLabel][$manualLabel] ?? 0 }}</td>
                                @endforeach
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </x-panel>

            <x-panel padding="p-6">
                <h2 class="text-sm font-semibold text-slate-100 mb-3">Confusion Matrix: Rule-based vs Manual</h2>
                <table class="w-full text-xs text-slate-300">
                    <thead class="text-slate-500 uppercase">
                        <tr><th class="text-left py-1">Rule bilang →</th><th>manual: positive</th><th>manual: neutral</th><th>manual: negative</th></tr>
                    </thead>
                    <tbody>
                        @foreach(['positive', 'neutral', 'negative'] as $ruleLabel)
                            <tr class="border-t border-slate-800">
                                <td class="py-1 font-semibold">{{ $ruleLabel }}</td>
                                @foreach(['positive', 'neutral', 'negative'] as $manualLabel)
                                    <td class="text-center">{{ $confusionRule[$ruleLabel][$manualLabel] ?? 0 }}</td>
                                @endforeach
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </x-panel>

            <div class="text-center">
                <a href="{{ route('sentiment-validation.index') }}" class="text-xs text-sky-400 hover:underline">← Lanjut label lagi</a>
            </div>
        @endif
    </div>
</x-app-layout>
