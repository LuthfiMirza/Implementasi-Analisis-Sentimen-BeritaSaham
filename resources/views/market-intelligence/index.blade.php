<x-app-layout>
    <div x-data="{ 
        showPromptModal: false, 
        copied: false,
        promptText: `Halo Antigravity, tolong jalankan analisis dan riset mendalam Market Intelligence untuk kondisi pasar bursa hari ini:

1. DIAGNOSA KUANTITATIF PASAR HARI INI:
   - Ambil data penutupan IHSG (^JKSE) hari ini: Open, High, Low, Close, Volume, dan % perubahan.
   - Hitung deviasi harga terhadap MA20, MA50, dan MA200.
   - Evaluasi nilai RSI(14) dan akselerasi MACD Histogram.
   - Uji Market Breadth pada 48 saham acuan (LQ45/IDX30): jumlah gainers, losers, unchanged, dan saham yang membentur batas ARB (7%).
   - Cek kurs penutupan USD/IDR dan dampaknya terhadap capital flow.

2. EVALUASI ATURAN DISIPLIN GEMINI.md (3 KUNCI REBOUND):
   - Kunci 1 (Candle Reversal): Apakah terbentuk hammer/pin bar/bullish engulfing hijau tebal dengan volume di atas MA20?
   - Kunci 2 (Market Breadth): Apakah jumlah gainers sudah melampaui > 50% bursa aktif?
   - Kunci 3 (Support Defense): Apakah support kunci bertahan minimal 2 hari bursa berturut-turut tanpa new low?
   - Tentukan STATUS REZIM PASAR saat ini (CASH IS KING / DEFENSIVE / REBOUND SPECULATIVE / REBOUND CONFIRMED).

3. INTELIJEN SENTIMEN BERITA & KATALIS:
   - Telusuri perkembangan berita sentimen terkini (kebijakan BEI/OJK, respon resmi MSCI, pergerakan dana asing, dan sentimen sektoral/komoditas).
   - Identifikasi apakah ada katalis yang meredakan atau memperparah kepanikan likuiditas.

4. AUDIT PORTOFOLIO & SINKRONISASI SISTEM:
   - Cek posisi terbuka di database MySQL / open_positions.json.
   - Pastikan kepatuhan Stop Loss (-3,5%), larangan averaging down (martingale), dan aturan batas waktu 10 hari.

5. PENCATATAN & GIT COMMIT ATOMIK:
   - Buat laporan riset baru di: reports/market_regime_research_YYYYMMDD.md
   - Perbarui log kronologis di: docs/trading-log.md
   - Perbarui memori permanen di: GEMINI.md
   - Lakukan commit dan push secara atomik ke origin/main dengan pesan commit terstandar.
   - Tampilkan ringkasan eksekutif beserta rekomendasi aksi konkret untuk sesi besok.`,
        copyToClipboard() {
            navigator.clipboard.writeText(this.promptText);
            this.copied = true;
            setTimeout(() => { this.copied = false; }, 2500);
        }
    }" class="space-y-6 max-w-7xl mx-auto px-2 sm:px-4 lg:px-0">
        
        {{-- Header Section --}}
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
            <div>
                <div class="flex items-center gap-2 mb-1">
                    <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-rose-500/20 text-rose-400 border border-rose-500/30">
                        Institutional Intelligence
                    </span>
                    <span class="text-xs text-slate-400 font-mono">
                        Sentimena Quant & Research Desk
                    </span>
                </div>
                <h1 class="text-2xl sm:text-3xl font-bold text-slate-100 tracking-tight font-heading">
                    Market Intelligence & Research Hub
                </h1>
                <p class="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl">
                    Kajian mendalam dinamika pasar saham Indonesia, audit rezim teknikal makro, intelijen sentimen media, serta pemodelan skenario rebound untuk perlindungan modal portofolio.
                </p>
            </div>
            <div class="flex flex-wrap items-center gap-2.5">
                <button type="button"
                        @click="showPromptModal = true"
                        class="px-3.5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-amber-500/20 to-cyan-500/20 hover:from-amber-500/30 hover:to-cyan-500/30 text-amber-300 border border-amber-500/40 flex items-center gap-1.5 transition shadow-lg shadow-amber-500/10 cursor-pointer">
                    <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    <span>Salin Prompt AI Harian</span>
                </button>

                <a href="{{ route('dashboard') }}" class="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 transition flex items-center gap-1.5 border border-slate-700/60">
                    <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                    </svg>
                    <span>Dashboard Utama</span>
                </a>
            </div>
        </div>

        {{-- Live Market Regime Alert Hero Card --}}
        <div class="relative overflow-hidden rounded-2xl border border-rose-500/40 bg-gradient-to-br from-rose-950/40 via-slate-900/90 to-slate-950 p-5 sm:p-6 shadow-2xl backdrop-blur-xl">
            <div class="absolute -right-16 -top-16 w-64 h-64 bg-rose-500/10 rounded-full blur-3xl pointer-events-none"></div>
            
            <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
                <div class="space-y-2 max-w-2xl">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-500/30 text-rose-300 border border-rose-500/50 animate-pulse">
                            <span class="w-2 h-2 rounded-full bg-rose-400"></span>
                            STATUS: {{ $latestRegime['status'] }}
                        </span>
                        <span class="text-xs text-slate-400 font-mono">Diperbarui: {{ $latestRegime['last_updated'] }}</span>
                    </div>
                    <h2 class="text-lg sm:text-xl font-bold text-white tracking-tight">
                        Fase Kapitulasi Sistemik: Penembusan Level 5.000 & Regulasi ARB 7%
                    </h2>
                    <p class="text-xs sm:text-sm text-slate-300 leading-relaxed">
                        Katalis ancaman evaluasi MSCI dan pelemahan Rupiah memicu tekanan jual masif. Sesuai aturan protokol <span class="font-mono text-rose-300">GEMINI.md</span>, seluruh strategi pantulan dilarang dientri hingga terpenuhinya 3 syarat konfirmasi rebound.
                    </p>
                </div>

                {{-- Key Indicator Grid --}}
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 sm:gap-3 w-full lg:w-auto">
                    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                        <div class="text-[10px] text-slate-400 font-mono uppercase">IHSG Close</div>
                        <div class="text-sm font-bold text-white mt-0.5">{{ $latestRegime['ihsg_close'] }}</div>
                        <div class="text-[11px] font-semibold text-rose-400">{{ $latestRegime['ihsg_change'] }}</div>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                        <div class="text-[10px] text-slate-400 font-mono uppercase">RSI (14)</div>
                        <div class="text-sm font-bold text-amber-300 mt-0.5">{{ $latestRegime['rsi_14'] }}</div>
                        <div class="text-[10px] text-slate-400">Oversold Ekstrem</div>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                        <div class="text-[10px] text-slate-400 font-mono uppercase">Deviasi MA20</div>
                        <div class="text-sm font-bold text-rose-400 mt-0.5">{{ $latestRegime['ma20_dev'] }}</div>
                        <div class="text-[10px] text-slate-400">Tren Jangka Pendek</div>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                        <div class="text-[10px] text-slate-400 font-mono uppercase">Target Rebound</div>
                        <div class="text-xs font-bold text-cyan-300 mt-0.5">Rabu-Kamis</div>
                        <div class="text-[10px] text-slate-400">21-22 Okt 2026</div>
                    </div>
                </div>
            </div>
        </div>

        {{-- Featured Article (Proyeksi Rebound) --}}
        @php
            $featured = collect($reports)->firstWhere('is_featured', true) ?? ($reports[0] ?? null);
        @endphp

        @if($featured)
            <div class="glass-card rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/[0.05] via-slate-900/80 to-slate-950 p-6 shadow-xl relative overflow-hidden group">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-3">
                    <div class="flex items-center gap-2">
                        <span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            ★ FEATURED RESEARCH BRIEFING
                        </span>
                        <span class="text-xs text-slate-400 font-mono">{{ $featured['date'] }}</span>
                        <span class="text-xs text-slate-500">• {{ $featured['read_time'] }} min read</span>
                    </div>
                    <span class="text-xs font-mono text-slate-400">File: {{ $featured['slug'] }}.md</span>
                </div>

                <a href="{{ route('market-intelligence.show', $featured['slug']) }}" class="block group">
                    <h2 class="text-xl sm:text-2xl font-bold text-white group-hover:text-amber-300 transition duration-150">
                        {{ $featured['title'] }}
                    </h2>
                </a>

                <p class="text-xs sm:text-sm text-slate-300 mt-2.5 leading-relaxed">
                    {{ $featured['summary'] }}
                </p>

                <div class="mt-5 flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-slate-800/80">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="text-xs text-slate-400 font-semibold">Poin Kunci:</span>
                        <span class="text-[11px] px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">Isu Evaluasi MSCI</span>
                        <span class="text-[11px] px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">Regulasi ARB 7% BEI</span>
                        <span class="text-[11px] px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">3 Skenario Rebound</span>
                        <span class="text-[11px] px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">Checklist 3 Kunci GEMINI.md</span>
                    </div>

                    <a href="{{ route('market-intelligence.show', $featured['slug']) }}"
                       class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition shadow-lg shadow-amber-500/20">
                        <span>Baca Analisis Lengkap & Skenario</span>
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                    </a>
                </div>
            </div>
        @endif

        {{-- All Research Reports Grid --}}
        <div>
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                    <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                    <span>Arsip Laporan Riset Kuantitatif</span>
                </h3>
                <span class="text-xs text-slate-400 font-mono">{{ count($reports) }} Laporan Tersedia</span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                @foreach($reports as $report)
                    <div class="glass-card rounded-2xl p-5 border border-slate-800 hover:border-slate-700 bg-slate-900/50 flex flex-col justify-between transition group">
                        <div>
                            <div class="flex items-center justify-between gap-2 mb-2">
                                <span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold font-mono tracking-wider uppercase bg-{{ $report['tag_color'] }}-500/10 text-{{ $report['tag_color'] }}-400 border border-{{ $report['tag_color'] }}-500/30">
                                    {{ $report['tag'] }}
                                </span>
                                <div class="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                                    <span>{{ $report['date'] }}</span>
                                    <span>•</span>
                                    <span>{{ $report['read_time'] }} min</span>
                                </div>
                            </div>

                            <a href="{{ route('market-intelligence.show', $report['slug']) }}" class="block">
                                <h4 class="text-sm sm:text-base font-bold text-slate-100 group-hover:text-cyan-400 transition line-clamp-2">
                                    {{ $report['title'] }}
                                </h4>
                            </a>

                            <p class="text-xs text-slate-400 mt-2 line-clamp-3 leading-relaxed">
                                {{ $report['summary'] }}
                            </p>
                        </div>

                        <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
                            <span class="text-[11px] text-slate-500 font-mono">{{ $report['file_size'] }}</span>
                            <a href="{{ route('market-intelligence.show', $report['slug']) }}"
                               class="text-cyan-400 hover:text-cyan-300 font-semibold inline-flex items-center gap-1 group-hover:translate-x-1 transition">
                                <span>Buka Ulasan</span>
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                                </svg>
                            </a>
                        </div>
                    </div>
                @endforeach
            </div>
        </div>

        {{-- Interactive Prompt Modal --}}
        <div x-show="showPromptModal" 
             x-cloak
             class="fixed inset-0 z-50 overflow-y-auto"
             aria-labelledby="modal-title" 
             role="dialog" 
             aria-modal="true">
            {{-- Backdrop --}}
            <div x-show="showPromptModal"
                 x-transition:enter="ease-out duration-300"
                 x-transition:enter-start="opacity-0"
                 x-transition:enter-end="opacity-100"
                 x-transition:leave="ease-in duration-200"
                 x-transition:leave-start="opacity-100"
                 x-transition:leave-end="opacity-0"
                 class="fixed inset-0 bg-slate-950/80 backdrop-blur-md transition-opacity"
                 @click="showPromptModal = false"></div>

            {{-- Modal Panel --}}
            <div class="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
                <div x-show="showPromptModal"
                     x-transition:enter="ease-out duration-300"
                     x-transition:enter-start="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
                     x-transition:enter-end="opacity-100 translate-y-0 sm:scale-100"
                     x-transition:leave="ease-in duration-200"
                     x-transition:leave-start="opacity-100 translate-y-0 sm:scale-100"
                     x-transition:leave-end="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
                     class="relative transform overflow-hidden rounded-2xl bg-slate-900 border border-amber-500/30 text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-2xl p-6">
                    
                    {{-- Modal Header --}}
                    <div class="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                            </div>
                            <div>
                                <h3 class="text-base font-bold text-white tracking-tight" id="modal-title">
                                    Master Prompt Riset Harian Sentimena AI
                                </h3>
                                <p class="text-xs text-slate-400 mt-0.5">
                                    Jalankan di Antigravity IDE setiap penutupan bursa (15:45 - 16:30 WIB)
                                </p>
                            </div>
                        </div>
                        <button type="button" 
                                @click="showPromptModal = false"
                                class="text-slate-400 hover:text-slate-200 transition p-1">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    {{-- Modal Body: Prompt Display --}}
                    <div class="my-4 space-y-3">
                        <div class="flex items-center justify-between text-xs text-slate-400">
                            <span>Teks Prompt Siap Pakai:</span>
                            <span class="text-[11px] font-mono text-cyan-400">Deep Quantitative & Risk Audit</span>
                        </div>

                        <div class="relative group">
                            <textarea readonly 
                                      x-text="promptText"
                                      rows="12"
                                      class="w-full rounded-xl bg-slate-950 border border-slate-800 p-3.5 text-xs font-mono text-slate-200 leading-relaxed focus:outline-none focus:border-amber-500/50 resize-none select-all"></textarea>
                        </div>

                        <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs text-slate-400 space-y-1">
                            <div class="font-semibold text-slate-300">💡 Alur Otomatis yang Dijalankan AI:</div>
                            <div>1. Mengambil data real-time IHSG, RSI, deviasi MA20/50/200, dan market breadth.</div>
                            <div>2. Mengaudit kepatuhan 3 Kunci Rebound sesuai <code class="text-rose-400 font-mono">GEMINI.md</code>.</div>
                            <div>3. Menyimpan laporan baru di <code class="text-cyan-400 font-mono">reports/</code> dan memperbarui log harian.</div>
                            <div>4. Melakukan commit & push secara atomik ke GitHub.</div>
                        </div>
                    </div>

                    {{-- Modal Footer --}}
                    <div class="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <span x-show="copied" 
                                  x-transition
                                  class="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                                </svg>
                                <span>Berhasil disalin ke clipboard! Siap di-paste ke chat Antigravity IDE.</span>
                            </span>
                        </div>

                        <div class="flex items-center gap-2">
                            <button type="button"
                                    @click="showPromptModal = false"
                                    class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
                                Tutup
                            </button>
                            <button type="button"
                                    @click="copyToClipboard()"
                                    class="px-5 py-2 rounded-xl text-xs font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center gap-1.5 transition shadow-lg shadow-amber-500/20 cursor-pointer">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                                </svg>
                                <span x-text="copied ? 'Tersalin!' : 'Salin ke Clipboard'"></span>
                            </button>
                        </div>
                    </div>

                </div>
            </div>
        </div>

    </div>
</x-app-layout>
