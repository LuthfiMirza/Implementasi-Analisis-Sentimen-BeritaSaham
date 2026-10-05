<x-app-layout>
<div class="space-y-6" x-data="{ activeFilter: 'all' }">

  {{-- ── HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5 flex items-center gap-2">
        <svg class="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
        </svg>
        Radar Log
        <span class="text-sm font-normal text-emerald-400/70 ml-1">SELF_RADAR_V1</span>
      </h1>
      <p class="text-sm text-slate-400 mt-1">Catat fill, skip, dan exit sinyal experimental. Bukan sinyal resmi.</p>
    </div>
    <a href="{{ route('trades.radar') }}"
       class="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-300 transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
      </svg>
      Signal Radar
    </a>
  </div>

  {{-- ── FLASH STATUS ── --}}
  @if(session('status'))
    <div class="glass-card border border-emerald-500/40 bg-emerald-500/[0.06] rounded-2xl px-4 py-3 text-sm text-emerald-300 flex items-center gap-2">
      <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      {{ session('status') }}
    </div>
  @endif

  {{-- ── KARTU RINGKASAN METRIK (MODAL RP 10 JUTA PER TRADE) ── --}}
  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
    {{-- Saldo Modal Berjalan --}}
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80 bg-slate-900/50">
      <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wider mb-1">Saldo Modal Berjalan</p>
      <p class="text-xl font-bold font-mono text-slate-100">
        Rp {{ number_format($stats['current_capital'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] mt-1 font-medium font-mono {{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
        {{ $stats['total_realized_pnl'] >= 0 ? '+' : '' }}{{ number_format($stats['total_capital_growth_pct'], 2) }}% dari Rp 10Jt
      </p>
    </div>

    {{-- Realized P&L Rp --}}
    <div class="glass-card rounded-2xl p-4 border {{ $stats['total_realized_pnl'] >= 0 ? 'border-emerald-500/30 bg-emerald-500/[0.03]' : 'border-rose-500/30 bg-rose-500/[0.03]' }}">
      <p class="text-[10px] uppercase font-semibold tracking-wider mb-1 {{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400/80' : 'text-rose-400/80' }}">
        Total Realized P&L
      </p>
      <p class="text-xl font-bold font-mono {{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
        {{ $stats['total_realized_pnl'] >= 0 ? '+' : '' }}Rp {{ number_format($stats['total_realized_pnl'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Modal Rp 10 Jt / trade</p>
    </div>

    {{-- Win Rate Live --}}
    <div class="glass-card rounded-2xl p-4 border border-amber-500/20 bg-amber-500/[0.02]">
      <p class="text-[10px] text-amber-400/80 uppercase font-semibold tracking-wider mb-1">Win Rate Live</p>
      <p class="text-xl font-bold font-mono text-amber-300">
        {{ $stats['win_rate'] !== null ? $stats['win_rate'].'%' : '—' }}
      </p>
      <p class="text-[11px] text-slate-400 mt-1 font-mono">
        <span class="text-emerald-400 font-bold">{{ $stats['win'] }}W</span> &times; <span class="text-rose-400 font-bold">{{ $stats['loss'] }}L</span>
        @if(($stats['draw'] ?? 0) > 0)
          &times; <span class="text-slate-400">{{ $stats['draw'] }}D</span>
        @endif
      </p>
    </div>

    {{-- Trade Ditutup --}}
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80 bg-slate-900/50">
      <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wider mb-1">Trade Selesai</p>
      <p class="text-xl font-bold font-mono text-slate-100">{{ $stats['closed'] }} Sinyal</p>
      @if($stats['avg_pnl'] !== null)
        <p class="text-[11px] mt-1 font-mono {{ $stats['avg_pnl'] >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
          avg {{ $stats['avg_pnl'] >= 0 ? '+' : '' }}{{ $stats['avg_pnl'] }}% / trade
        </p>
      @endif
    </div>

    {{-- Posisi Terbuka --}}
    <div class="glass-card rounded-2xl p-4 border border-sky-500/20 bg-sky-500/[0.03]">
      <p class="text-[10px] text-sky-400/80 uppercase font-semibold tracking-wider mb-1 flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse"></span> Posisi Terbuka
      </p>
      <p class="text-xl font-bold font-mono text-sky-400">{{ $stats['open'] }} Posisi</p>
      <p class="text-[11px] text-sky-400/70 mt-1">TEBE (Hold)</p>
    </div>

    {{-- Rentang Periode Data --}}
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80 bg-slate-900/50">
      <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wider mb-1">Rentang Data</p>
      <p class="text-xs font-bold font-mono text-slate-200 mt-1.5 leading-tight">{{ $stats['date_range_label'] }}</p>
      <p class="text-[11px] text-slate-500 mt-1">{{ $stats['total'] }} total sinyal masuk</p>
    </div>
  </div>

  {{-- ── DISCLAIMER ── --}}
  <div class="glass-card border border-amber-500/30 bg-amber-500/[0.04] rounded-2xl px-4 py-3">
    <p class="text-xs text-amber-300 flex items-start gap-2">
      <svg class="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
      </svg>
      <span>
        <strong>Catatan eksperimental.</strong> Angka sinyal adalah estimasi harga saat pertama terdeteksi — bukan harga fill aktual.
        Isi <em>fill_price</em> dengan harga yang benar-benar kamu bayar saat beli.
        Belum ada pencatatan = sinyal belum diputuskan (bisa diisi fill atau skip kapan saja).
      </span>
    </p>
  </div>

  {{-- ── SEKSI: TOP 5 EMITEN PENCETAK CUAN TERBESAR ── --}}
  @if(!empty($topPerformers) && $topPerformers->count() > 0)
    <div class="glass-card rounded-2xl border border-emerald-500/30 bg-emerald-500/[0.02] p-4 space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold text-slate-100 flex items-center gap-2">
          <span>🏆</span> Top 5 Emiten Pencetak Cuan Terbesar (SELF_RADAR_V1)
        </h2>
        <span class="text-[11px] text-slate-400">Modal Sizing Rp 10 Jt / Trade</span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2.5">
        @foreach($topPerformers as $idx => $tp)
          @php
            $medals = ['🥇', '🥈', '🥉', '⭐', '⭐'];
            $medal = $medals[$idx] ?? '⭐';
          @endphp
          <div class="rounded-xl p-3 bg-slate-900/70 border border-slate-800 text-center">
            <div class="flex items-center justify-center gap-1 mb-1">
              <span>{{ $medal }}</span>
              <span class="font-bold text-slate-100 text-sm">#{{ $tp['ticker'] }}</span>
            </div>
            <p class="text-xs font-mono font-bold text-emerald-400">
              +Rp {{ number_format($tp['tot_pnl_rp'], 0, ',', '.') }}
            </p>
            <p class="text-[10px] text-emerald-300/80 font-mono font-semibold">
              +{{ number_format($tp['tot_pnl_pct'], 2) }}% akumulasi
            </p>
            <p class="text-[10px] text-slate-400 mt-1">
              {{ $tp['trades'] }} Trade (WR {{ $tp['win_rate'] }}%)
            </p>
          </div>
        @endforeach
      </div>
    </div>
  @endif

  {{-- ── FILTER CEPAT ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
    <div class="flex items-center gap-2">
      <span class="text-xs font-semibold text-slate-400">Filter Tampilan:</span>
      <div class="inline-flex rounded-xl bg-slate-900/80 p-1 border border-slate-800">
        <button type="button" @click="activeFilter = 'all'"
                :class="activeFilter === 'all' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200'"
                class="px-3 py-1 text-xs font-semibold rounded-lg transition">
          Semua ({{ $stats['total'] }})
        </button>
        <button type="button" @click="activeFilter = 'win'"
                :class="activeFilter === 'win' ? 'bg-emerald-600 text-white shadow' : 'text-emerald-400 hover:text-emerald-300'"
                class="px-3 py-1 text-xs font-semibold rounded-lg transition flex items-center gap-1">
          <span>🟢</span> Cuan Saja ({{ $stats['win'] }})
        </button>
        <button type="button" @click="activeFilter = 'loss'"
                :class="activeFilter === 'loss' ? 'bg-rose-600 text-white shadow' : 'text-rose-400 hover:text-rose-300'"
                class="px-3 py-1 text-xs font-semibold rounded-lg transition flex items-center gap-1">
          <span>🔴</span> Loss Saja ({{ $stats['loss'] }})
        </button>
        <button type="button" @click="activeFilter = 'open'"
                :class="activeFilter === 'open' ? 'bg-sky-600 text-white shadow' : 'text-sky-400 hover:text-sky-300'"
                class="px-3 py-1 text-xs font-semibold rounded-lg transition flex items-center gap-1">
          <span>🔵</span> Open Saja ({{ $stats['open'] }})
        </button>
      </div>
    </div>
  </div>

  {{-- ── TABEL LOG ── --}}
  @php
    $byDate = $logs->groupBy(fn($l) => $l->signal_date->format('Y-m-d'));
  @endphp

  @foreach($byDate as $date => $group)
    @php
      $dateLabel = \Carbon\Carbon::parse($date)->locale('id')->isoFormat('dddd, D MMMM YYYY');
      $hasBuy = $group->where('result', '!=', 'SKIP')->whereNull('fill_price')->filter(fn($l) => $l->result !== 'SKIP')->count() > 0;
    @endphp

    <div class="space-y-2">
      <div class="flex items-center gap-3">
        <h2 class="text-sm font-semibold text-slate-400 uppercase tracking-wider">{{ $dateLabel }}</h2>
        <div class="flex-1 h-px bg-slate-800"></div>
        <span class="text-[10px] text-slate-500">{{ $group->count() }} sinyal</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        @foreach($group as $log)
          @php
            $isFilled  = !is_null($log->fill_price);
            $isExited  = !is_null($log->exit_price);
            $isSkipped = $log->result === 'SKIP';
            $isWin     = $log->result === 'WIN';
            $isLoss    = $log->result === 'LOSS';
          @endphp

          <div x-show="activeFilter === 'all' || (activeFilter === 'win' && {{ $isWin ? 'true' : 'false' }}) || (activeFilter === 'loss' && {{ $isLoss ? 'true' : 'false' }}) || (activeFilter === 'open' && {{ ($isFilled && !$isExited) ? 'true' : 'false' }})"
               class="glass-card rounded-2xl p-4 border-2 transition-colors
            @if($isWin) border-green-500/40 bg-green-500/[0.04]
            @elseif($isLoss) border-rose-500/40 bg-rose-500/[0.04]
            @elseif($isSkipped) border-slate-700/50 opacity-60
            @elseif($isFilled) border-sky-500/40 bg-sky-500/[0.04]
            @else border-emerald-500/30 bg-emerald-500/[0.03]
            @endif">

            {{-- Header kartu --}}
            <div class="flex items-start justify-between mb-3">
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-lg font-bold text-slate-100">{{ $log->ticker }}</span>
                  @if($log->rank)
                    <span class="text-[10px] text-slate-500 font-mono">#{{ $log->rank }}</span>
                  @endif
                </div>
                <p class="text-xs text-slate-500 mt-0.5">
                  Score: <span class="text-slate-300 font-mono">{{ $log->score ?? '—' }}</span>
                </p>
              </div>
              <span class="text-[10px] px-2 py-1 rounded-full font-semibold
                @if($isWin) bg-green-500/20 text-green-300 border border-green-500/40
                @elseif($isLoss) bg-rose-500/20 text-rose-300 border border-rose-500/40
                @elseif($isSkipped) bg-slate-700 text-slate-400 border border-slate-600
                @elseif($isFilled && !$isExited) bg-sky-500/20 text-sky-300 border border-sky-500/40
                @else bg-emerald-500/20 text-emerald-300 border border-emerald-500/40
                @endif">
                @if($isWin) 🟢 WIN
                @elseif($isLoss) 🔴 LOSS
                @elseif($isSkipped) ⏭️ SKIP
                @elseif($isFilled && !$isExited) 🔵 OPEN
                @else ⏳ BELUM DIISI
                @endif
              </span>
            </div>

            {{-- Peringatan Risiko Suspensi / High Volatility --}}
            @php
              $isSuspensionRisk = ($log->ret_5d_pct !== null && (float)$log->ret_5d_pct >= 20.0) && ($log->rsi14 !== null && (float)$log->rsi14 >= 75.0);
            @endphp
            @if($isSuspensionRisk)
              <div class="mb-3 px-2.5 py-1.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-[11px] text-rose-300 font-semibold flex items-center gap-1.5 shadow-sm shadow-rose-950/40">
                <span class="text-sm shrink-0">⚠️</span>
                <div>
                  <span class="block text-rose-200 uppercase tracking-wider text-[10px] font-bold">HIGH VOLATILITY / RISIKO SUSPENSI</span>
                  <span class="text-[10px] text-rose-300 font-normal">Wajib <strong>Same-Day Exit</strong> (Jual sebelum 15:50 WIB, dilarang inapkan).</span>
                </div>
              </div>
            @endif

            {{-- Metrik sinyal --}}
            <div class="grid grid-cols-3 gap-2 text-[11px] mb-3">
              <div>
                <p class="text-slate-500">Harga Sinyal</p>
                <p class="font-mono text-slate-200 font-semibold">
                  Rp{{ number_format($log->price_at_first_seen, 0, ',', '.') }}
                </p>
              </div>
              <div>
                <p class="text-slate-500">RSI14</p>
                <p class="font-mono {{ $log->rsi14 >= 70 ? 'text-amber-400' : 'text-slate-200' }}">
                  {{ $log->rsi14 ?? '—' }}
                </p>
              </div>
              <div>
                <p class="text-slate-500">ret_5d</p>
                <p class="font-mono text-emerald-400">+{{ $log->ret_5d_pct ?? '—' }}%</p>
              </div>
            </div>

            {{-- Fill & Exit info --}}
            @if($isFilled || $isExited)
              <div class="rounded-xl bg-slate-800/60 p-2.5 mb-3 space-y-1.5 text-[11px]">
                @if($isFilled)
                  <div class="flex justify-between">
                    <span class="text-slate-400">Fill</span>
                    <span class="font-mono text-slate-100">
                      Rp{{ number_format($log->fill_price, 0, ',', '.') }}
                      <span class="text-slate-500 ml-1">{{ $log->filled_at?->format('d/m H:i') }}</span>
                    </span>
                  </div>
                @endif
                @if($isExited)
                  <div class="flex justify-between">
                    <span class="text-slate-400">Exit</span>
                    <span class="font-mono text-slate-100">
                      Rp{{ number_format($log->exit_price, 0, ',', '.') }}
                      <span class="text-slate-500 ml-1">{{ $log->exited_at?->format('d/m H:i') }}</span>
                    </span>
                  </div>
                  @if($log->pnl_pct !== null)
                    @php
                      $cardPnlRp = ($baseCapital ?? 10000000) * ($log->pnl_pct / 100);
                    @endphp
                    <div class="flex justify-between items-center font-semibold pt-1 border-t border-slate-700/50">
                      <span class="text-slate-400">PnL (Rp 10Jt):</span>
                      <div class="text-right">
                        <span class="font-mono {{ $log->pnl_pct >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                          {{ $log->pnl_pct >= 0 ? '+' : '' }}{{ $log->pnl_pct }}%
                        </span>
                        <span class="block text-[10px] font-mono {{ $cardPnlRp >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
                          {{ $cardPnlRp >= 0 ? '+' : '' }}Rp {{ number_format($cardPnlRp, 0, ',', '.') }}
                        </span>
                      </div>
                    </div>
                  @endif
                @endif
              </div>
            @endif

            {{-- Panduan Exit Dinamis untuk Posisi OPEN --}}
            @if($isFilled && !$isExited)
              @php
                $bepPrice = round($log->fill_price * 1.008);
                $lotSizing = floor(($baseCapital ?? 10000000) / ($log->fill_price * 100 * 1.0015));
                $valSizing = $lotSizing * 100 * $log->fill_price;
              @endphp
              <div class="flex items-center justify-between text-[11px] px-2.5 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 mb-2.5 text-slate-300">
                <span class="text-slate-400">Sizing Modal Rp 10 Jt:</span>
                <span class="font-mono font-bold text-amber-300">{{ number_format($lotSizing) }} Lot <span class="text-slate-500 font-normal text-[10px]">(Rp {{ number_format($valSizing, 0, ',', '.') }})</span></span>
              </div>
              <div class="rounded-xl border p-2.5 mb-3 text-[11px] space-y-1.5 {{ $isSuspensionRisk ? 'bg-rose-500/10 border-rose-500/30 text-rose-200' : 'bg-sky-500/10 border-sky-500/30 text-sky-200' }}">
                <div class="flex items-center justify-between font-bold">
                  <span class="flex items-center gap-1">
                    <span>🎯</span> Panduan Rencana Exit:
                  </span>
                  @if($isSuspensionRisk)
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/30 text-rose-200 uppercase font-mono">Wajib Hari Ini</span>
                  @else
                    <span class="text-[10px] text-sky-300 font-mono">Trailing Stop 1%</span>
                  @endif
                </div>

                <div class="space-y-1 text-[10px] text-slate-300">
                  @if($isSuspensionRisk)
                    <p class="text-rose-300 font-medium">
                      ⚠️ <strong>Lonjakan ekstrem terdeteksi.</strong> Wajib Take Profit sebelum penutupan sesi 2 (15:40–15:50 WIB) untuk hindari gembok suspensi BEI.
                    </p>
                  @else
                    <div class="flex justify-between">
                      <span class="text-slate-400">Jadwal Trailing:</span>
                      <span class="font-mono text-slate-200">{{ $log->trailing_start_at?->format('d/m H:i') ?? 'Besok 09:30' }} WIB</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-slate-400">Proteksi Break-Even (BEP):</span>
                      <span class="font-mono text-emerald-400">Rp{{ number_format($bepPrice, 0, ',', '.') }} (+0.8%)</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-slate-400">Ambang Keluar:</span>
                      <span class="font-mono text-amber-300">1.0% di bawah Puncak (Peak)</span>
                    </div>
                  @endif
                </div>
              </div>
            @endif

            {{-- First seen --}}
            <p class="text-[10px] text-slate-600 mb-3">
              Deteksi: {{ $log->first_seen_at?->format('H:i') }} — {{ $log->last_seen_at?->format('H:i') }} WIB
            </p>

            {{-- ACTIONS --}}
            @if(!$isSkipped && !$isExited)
              <div class="space-y-2" x-data="{ showFill: false, showExit: false }">

                @if(!$isFilled)
                  {{-- Tombol Catat Fill --}}
                  <button type="button" @click="showFill = !showFill"
                          class="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl
                                 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300
                                 border border-emerald-500/40 text-xs font-semibold transition">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                    Catat Fill (Beli)
                  </button>

                  <div x-show="showFill" x-cloak x-transition>
                    <form method="POST" action="{{ route('trades.radar-log.fill', $log) }}" class="space-y-2 rounded-xl border border-emerald-500/30 bg-slate-900/60 p-3 mt-1">
                      @csrf
                      <div class="flex gap-2">
                        <div class="flex-1">
                          <label class="text-[10px] text-slate-400 block mb-1">Harga Fill (Rp)</label>
                          <input type="number" name="fill_price"
                                 value="{{ $log->price_at_first_seen }}"
                                 min="1" step="1" required
                                 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-mono text-slate-100 focus:outline-none focus:border-emerald-500">
                        </div>
                        <div class="flex-1">
                          <label class="text-[10px] text-slate-400 block mb-1">Waktu Fill</label>
                          <input type="datetime-local" name="filled_at"
                                 value="{{ now()->format('Y-m-d\TH:i') }}"
                                 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-emerald-500">
                        </div>
                      </div>
                      <div class="flex gap-2">
                        <button type="submit" class="flex-1 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold transition">
                          ✅ Simpan Fill
                        </button>
                        <button type="button" @click="showFill = false" class="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs transition">
                          Batal
                        </button>
                      </div>
                    </form>
                  </div>
                @else
                  {{-- Sudah fill, tampilkan tombol Exit --}}
                  <button type="button" @click="showExit = !showExit"
                          class="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl
                                 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300
                                 border border-sky-500/40 text-xs font-semibold transition">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
                    </svg>
                    Catat Exit / Jual
                  </button>

                  <div x-show="showExit" x-cloak x-transition>
                    <form method="POST" action="{{ route('trades.radar-log.exit', $log) }}" class="space-y-2 rounded-xl border border-sky-500/30 bg-slate-900/60 p-3 mt-1">
                      @csrf
                      <div class="flex gap-2">
                        <div class="flex-1">
                          <label class="text-[10px] text-slate-400 block mb-1">Harga Exit (Rp)</label>
                          <input type="number" name="exit_price"
                                 min="1" step="1" required
                                 value="{{ $log->latest_price ? (int)$log->latest_price : '' }}"
                                 placeholder="Misal: {{ $log->latest_price ? (int)$log->latest_price : 3800 }}"
                                 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-mono text-slate-100 focus:outline-none focus:border-sky-500">
                        </div>
                        <div class="flex-1">
                          <label class="text-[10px] text-slate-400 block mb-1">Waktu Exit</label>
                          <input type="datetime-local" name="exited_at"
                                 value="{{ now()->format('Y-m-d\TH:i') }}"
                                 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500">
                        </div>
                      </div>
                      <input type="text" name="exit_reason" placeholder="Alasan exit (opsional, mis: trailing stop kena)"
                             class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500">
                      <div class="flex gap-2">
                        <button type="submit" class="flex-1 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold transition">
                          💾 Simpan Exit
                        </button>
                        <button type="button" @click="showExit = false" class="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs transition">
                          Batal
                        </button>
                      </div>
                    </form>
                  </div>
                @endif

                {{-- Tombol Skip --}}
                @if(!$isFilled)
                  <form method="POST" action="{{ route('trades.radar-log.skip', $log) }}"
                        onsubmit="return confirm('Tandai {{ $log->ticker }} sebagai SKIP (tidak jadi beli)?')">
                    @csrf
                    <button type="submit"
                            class="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-xl
                                   bg-slate-700/50 hover:bg-slate-700 text-slate-400 hover:text-slate-300
                                   border border-slate-700 text-xs transition">
                      ⏭️ Skip (Tidak Jadi Beli)
                    </button>
                  </form>
                @endif

              </div>

            @elseif($isSkipped)
              {{-- Bisa undo skip --}}
              <form method="POST" action="{{ route('trades.radar-log.fill', $log) }}">
                @csrf
                <input type="hidden" name="fill_price" value="{{ $log->price_at_first_seen }}">
                <button type="submit" class="w-full text-xs text-slate-500 hover:text-slate-300 py-1.5 transition">
                  ↩ Batalkan skip & isi fill dengan harga sinyal
                </button>
              </form>
            @endif

          </div>
        @endforeach
      </div>
    </div>
  @endforeach

  @if($logs->isEmpty())
    <div class="glass-card border border-slate-800/80 rounded-2xl p-10 text-center text-slate-500">
      <svg class="w-10 h-10 mx-auto mb-3 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
      </svg>
      <p class="text-sm">Belum ada log sinyal. Buka <a href="{{ route('trades.radar') }}" class="text-emerald-400 hover:underline">Signal Radar</a> untuk melihat sinyal aktif hari ini.</p>
    </div>
  @endif

</div>
</x-app-layout>
