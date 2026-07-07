<x-app-layout>
    <div class="max-w-3xl mx-auto space-y-4" x-data="sentimentValidation()" x-init="init()">
        <x-panel padding="p-6">
            <p class="text-xs uppercase text-slate-400">Validasi Kualitas Sentimen (Gap 2)</p>
            <h1 class="text-2xl font-bold text-slate-100">Label Manual: ML vs Rule-based</h1>
            <p class="text-sm text-slate-400 mt-2">
                Artikel di bawah ini adalah kasus di mana model ML dan rule-based BERBEDA PENDAPAT soal sentimen
                ({{ $totalDisagreements }} artikel total). Baca judul + ringkasan, lalu pilih menurut kamu artikel ini
                nadanya positif/netral/negatif untuk emitennya. Progres tersimpan otomatis per artikel.
            </p>
            <div class="mt-3 text-sm text-slate-300">
                Sudah dilabel: <span class="font-semibold" x-text="progress.labeled ?? {{ $labeledByUser }}"></span>
                / <span x-text="progress.total ?? {{ $totalDisagreements }}"></span>
            </div>
        </x-panel>

        <template x-if="done">
            <x-panel padding="p-6" class="text-center">
                <p class="text-lg font-semibold text-slate-100">Semua artikel disagreement sudah kamu label 🎉</p>
                <a href="{{ route('sentiment-validation.summary') }}" class="inline-block mt-4 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-900 font-semibold text-sm">
                    Lihat Ringkasan Hasil
                </a>
            </x-panel>
        </template>

        <template x-if="!done && article">
            <x-panel padding="p-6" class="space-y-4">
                <div>
                    <p class="text-[11px] uppercase text-slate-500" x-text="article.source"></p>
                    <h2 class="text-lg font-semibold text-slate-100 mt-1" x-text="article.title"></h2>
                    <p class="text-sm text-slate-300 mt-3 leading-relaxed" x-text="article.summary"></p>
                </div>

                <div class="grid grid-cols-3 gap-3">
                    <button @click="label('positive')" class="py-4 rounded-lg bg-green-500/15 border border-green-500/30 text-green-300 font-semibold hover:bg-green-500/25 transition">
                        ▲ Positif <span class="block text-[11px] text-green-300/60 mt-1">tekan 1</span>
                    </button>
                    <button @click="label('neutral')" class="py-4 rounded-lg bg-slate-700/50 border border-slate-600 text-slate-200 font-semibold hover:bg-slate-700 transition">
                        ◆ Netral <span class="block text-[11px] text-slate-400 mt-1">tekan 2</span>
                    </button>
                    <button @click="label('negative')" class="py-4 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-300 font-semibold hover:bg-rose-500/25 transition">
                        ▼ Negatif <span class="block text-[11px] text-rose-300/60 mt-1">tekan 3</span>
                    </button>
                </div>

                <p class="text-xs text-slate-500 text-center">Bisa juga pakai tombol angka 1/2/3 di keyboard.</p>
            </x-panel>
        </template>

        <div class="text-center">
            <a href="{{ route('sentiment-validation.summary') }}" class="text-xs text-sky-400 hover:underline">Lihat ringkasan sejauh ini →</a>
        </div>
    </div>

    <script>
        function sentimentValidation() {
            return {
                article: null,
                progress: {},
                done: false,
                submitting: false,
                init() {
                    this.loadNext();
                    window.addEventListener('keydown', (e) => {
                        if (this.submitting || this.done || !this.article) return;
                        if (e.key === '1') this.label('positive');
                        if (e.key === '2') this.label('neutral');
                        if (e.key === '3') this.label('negative');
                    });
                },
                async loadNext() {
                    const res = await fetch('{{ route('sentiment-validation.next') }}');
                    const data = await res.json();
                    if (data.done) {
                        this.done = true;
                        this.article = null;
                        return;
                    }
                    this.article = data.article;
                    this.progress = data.progress;
                },
                async label(value) {
                    if (this.submitting || !this.article) return;
                    this.submitting = true;
                    await fetch('{{ route('sentiment-validation.store') }}', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        },
                        body: JSON.stringify({ news_article_id: this.article.id, label: value }),
                    });
                    this.submitting = false;
                    await this.loadNext();
                },
            };
        }
    </script>
</x-app-layout>
