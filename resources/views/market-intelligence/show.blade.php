<x-app-layout>
    <div class="space-y-6 max-w-7xl mx-auto px-2 sm:px-4 lg:px-0">

        {{-- Breadcrumb & Top Bar --}}
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <nav class="flex items-center gap-2 text-xs text-slate-400">
                <a href="{{ route('dashboard') }}" class="hover:text-slate-200 transition">Dashboard</a>
                <span>/</span>
                <a href="{{ route('market-intelligence.index') }}" class="hover:text-slate-200 transition">Market Intelligence</a>
                <span>/</span>
                <span class="text-slate-200 font-semibold truncate max-w-xs">{{ $metadata['slug'] }}</span>
            </nav>

            <div class="flex items-center gap-2">
                <button type="button" onclick="window.print()" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition">
                    <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                    </svg>
                    <span>Cetak Dokumen</span>
                </button>
                <a href="{{ route('market-intelligence.index') }}" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 flex items-center gap-1.5 transition">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                    </svg>
                    <span>Semua Riset</span>
                </a>
            </div>
        </div>

        {{-- Article Title Card --}}
        <div class="glass-card rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 space-y-4">
            <div class="flex flex-wrap items-center gap-2 text-xs">
                <span class="px-2.5 py-1 rounded-md text-[10px] font-bold font-mono tracking-wider uppercase bg-{{ $metadata['tag_color'] }}-500/15 text-{{ $metadata['tag_color'] }}-400 border border-{{ $metadata['tag_color'] }}-500/30">
                    {{ $metadata['tag'] }}
                </span>
                <span class="text-slate-400 font-mono">{{ $metadata['date'] }}</span>
                <span class="text-slate-500">•</span>
                <span class="text-slate-400 font-mono">{{ $metadata['read_time'] }} menit waktu baca</span>
                <span class="text-slate-500">•</span>
                <span class="text-slate-400 font-mono">Status: <span class="text-rose-400 font-bold">{{ $metadata['regime'] }}</span></span>
            </div>

            <h1 class="text-2xl sm:text-3xl lg:text-4xl font-bold text-slate-100 tracking-tight font-heading leading-tight">
                {{ $metadata['title'] }}
            </h1>

            <div class="pt-4 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-400">
                <div class="flex items-center gap-2">
                    <div class="w-7 h-7 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold text-xs">
                        SI
                    </div>
                    <span>Diterbitkan oleh <strong class="text-slate-200">Sentimena Quantitative Research Team</strong></span>
                </div>
                <div class="font-mono text-[11px] text-slate-500">
                    Arsip Sistem: reports/{{ $metadata['slug'] }}.md
                </div>
            </div>
        </div>

        {{-- Main Article Grid (Content + Sticky Sidebar) --}}
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            
            {{-- Left: Article Body --}}
            <article class="lg:col-span-8 glass-card rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8 space-y-6 text-slate-300 leading-relaxed text-sm prose-invert max-w-none">
                <style>
                    .research-content h1 { font-size: 1.5rem; font-weight: 700; color: #f8fafc; margin-top: 1.5rem; margin-bottom: 0.75rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
                    .research-content h2 { font-size: 1.25rem; font-weight: 700; color: #38bdf8; margin-top: 1.75rem; margin-bottom: 0.75rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.35rem; }
                    .research-content h3 { font-size: 1.05rem; font-weight: 600; color: #f1f5f9; margin-top: 1.25rem; margin-bottom: 0.5rem; }
                    .research-content p { margin-bottom: 1rem; line-height: 1.7; color: #cbd5e1; }
                    .research-content ul { list-style-type: disc; margin-left: 1.5rem; margin-bottom: 1rem; space-y: 0.25rem; }
                    .research-content ol { list-style-type: decimal; margin-left: 1.5rem; margin-bottom: 1rem; }
                    .research-content li { margin-bottom: 0.35rem; }
                    .research-content hr { border-color: #1e293b; margin: 1.5rem 0; }
                    .research-content strong { color: #f8fafc; font-weight: 600; }
                    .research-content em { color: #94a3b8; font-style: italic; }
                </style>
                <div class="research-content">
                    {!! $htmlContent !!}
                </div>
            </article>

            {{-- Right: Sticky Tactical Action Panel --}}
            <aside class="lg:col-span-4 space-y-5 sticky top-6">
                
                {{-- Institutional Discipline Card --}}
                <div class="rounded-2xl border border-rose-500/40 bg-gradient-to-br from-rose-950/30 to-slate-900/80 p-5 shadow-xl space-y-3.5 backdrop-blur-md">
                    <div class="flex items-center justify-between">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-rose-400 font-mono">
                            Protokol Disiplin GEMINI.md
                        </span>
                        <span class="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                    </div>

                    <h3 class="text-sm font-bold text-white">
                        Aturan Rezim Crash & Eksekusi Portofolio
                    </h3>

                    <ul class="text-xs space-y-2 text-slate-300">
                        <li class="flex items-start gap-2">
                            <span class="text-rose-400 font-bold shrink-0">1.</span>
                            <span><strong>CASH IS KING:</strong> Dilarang belanja spekulatif sebelum 3 syarat konfirmasi terpenuhi.</span>
                        </li>
                        <li class="flex items-start gap-2">
                            <span class="text-rose-400 font-bold shrink-0">2.</span>
                            <span><strong>Anti-Martingale:</strong> Dilarang keras melakukan <em>averaging down</em> pada posisi merugi.</span>
                        </li>
                        <li class="flex items-start gap-2">
                            <span class="text-rose-400 font-bold shrink-0">3.</span>
                            <span><strong>Disiplin Cut Loss:</strong> Batas keras stop loss -3,5% wajib dieksekusi tanpa kompromi.</span>
                        </li>
                        <li class="flex items-start gap-2">
                            <span class="text-rose-400 font-bold shrink-0">4.</span>
                            <span><strong>Target Waktu 10 Hari:</strong> Posisi strategi gabungan wajib take profit di hari ke-10.</span>
                        </li>
                    </ul>

                    <div class="pt-3 border-t border-rose-500/20 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                        <span>Filter: Crash Guard</span>
                        <span class="text-emerald-400">Aktif & Dipatuhi</span>
                    </div>
                </div>

                {{-- 3 Rebound Keys Checklist --}}
                <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
                    <h3 class="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono flex items-center gap-1.5">
                        <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                        </svg>
                        <span>Checklist 3 Syarat Rebound</span>
                    </h3>

                    <div class="space-y-2.5 text-xs">
                        <div class="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                            <div class="flex items-center justify-between font-semibold text-slate-200">
                                <span>1. Reversal Candle IHSG</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">Belum</span>
                            </div>
                            <p class="text-[11px] text-slate-400 mt-1">Hammer / Bullish Engulfing hijau tebal + volume > MA20.</p>
                        </div>

                        <div class="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                            <div class="flex items-center justify-between font-semibold text-slate-200">
                                <span>2. Market Breadth > 50%</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">Belum (12,5%)</span>
                            </div>
                            <p class="text-[11px] text-slate-400 mt-1">Mayoritas saham aktif bursa ditutup menghijau.</p>
                        </div>

                        <div class="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                            <div class="flex items-center justify-between font-semibold text-slate-200">
                                <span>3. Support Defense 2 Hari</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">Belum</span>
                            </div>
                            <p class="text-[11px] text-slate-400 mt-1">Support 4.900 terbukti bertahan tanpa mencetak new low.</p>
                        </div>
                    </div>
                </div>

                {{-- Other Reports List --}}
                <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 space-y-3">
                    <h3 class="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
                        Laporan Riset Lainnya
                    </h3>
                    <div class="space-y-2">
                        @foreach($otherReports as $other)
                            <a href="{{ route('market-intelligence.show', $other['slug']) }}"
                               class="block p-3 rounded-xl bg-slate-950/40 hover:bg-slate-800/60 border border-slate-850 hover:border-slate-700 transition group">
                                <div class="text-[10px] font-mono text-slate-400">{{ $other['date'] }}</div>
                                <div class="text-xs font-semibold text-slate-200 group-hover:text-cyan-400 transition mt-0.5 line-clamp-2">
                                    {{ $other['title'] }}
                                </div>
                            </a>
                        @endforeach
                    </div>
                </div>

            </aside>

        </div>

    </div>
</x-app-layout>
