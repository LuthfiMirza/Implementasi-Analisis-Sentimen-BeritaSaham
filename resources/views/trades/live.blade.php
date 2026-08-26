<x-app-layout>
<div class="space-y-6" x-data="livePositionMonitor(@js($positions))">

  {{-- ── HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5 flex items-center gap-2">
        ⚡ Live Monitor
        <span class="relative flex h-2.5 w-2.5">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500"></span>
        </span>
      </h1>
      <p class="text-sm text-slate-400 mt-1">
        Harga live, jarak ke trailing stop, sisa hari ke target waktu -- auto-refresh tiap 30 detik.
      </p>
    </div>
    <div class="flex items-center gap-2 text-xs text-slate-500">
      <span x-show="loading" x-cloak class="text-sky-400">Memuat...</span>
      <span>Update terakhir: <span x-text="lastUpdateLabel" class="text-slate-300 font-mono"></span></span>
      <button type="button" @click="fetchData()"
              class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition"
              title="Refresh sekarang">
        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
      </button>
    </div>
  </div>

  {{-- ── RINGKASAN CEPAT ── --}}
  <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Posisi Terbuka</p>
      <p class="text-2xl font-bold text-slate-100" x-text="positions.length"></p>
    </div>
    <div class="glass-card rounded-2xl p-4 border border-rose-500/20 bg-rose-500/[0.03]">
      <p class="text-[10px] text-rose-400/80 uppercase font-medium mb-1">🔴 Bahaya (&le;1% ke SL)</p>
      <p class="text-2xl font-bold text-rose-400" x-text="countByStatus('danger')"></p>
    </div>
    <div class="glass-card rounded-2xl p-4 border border-amber-500/20 bg-amber-500/[0.03]">
      <p class="text-[10px] text-amber-400/80 uppercase font-medium mb-1">🟡 Waspada (&le;3% ke SL)</p>
      <p class="text-2xl font-bold text-amber-400" x-text="countByStatus('warning')"></p>
    </div>
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Total Floating PnL</p>
      <p class="text-xl font-bold font-mono"
         :class="totalFloatingPnl() >= 0 ? 'text-green-400' : 'text-rose-400'"
         x-text="(totalFloatingPnl() >= 0 ? '+' : '') + 'Rp' + Math.round(totalFloatingPnl()).toLocaleString('id-ID')"></p>
    </div>
  </div>

  {{-- ── EMPTY STATE ── --}}
  <div x-show="positions.length === 0" x-cloak
       class="glass-card border border-slate-800/80 rounded-2xl p-10 text-center text-slate-500">
    Tidak ada posisi terbuka saat ini.
  </div>

  {{-- ── CARDS POSISI (diurutkan paling urgent dulu, dari server) ── --}}
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <template x-for="p in positions" :key="p.id">
      <div class="glass-card rounded-2xl p-5 border-2 transition-colors"
           :class="{
             'border-rose-500/50 bg-rose-500/[0.04]': p.status === 'danger',
             'border-amber-500/40 bg-amber-500/[0.03]': p.status === 'warning',
             'border-slate-800/80': p.status === 'safe' || p.status === 'unknown',
           }">

        {{-- Header: ticker + strategi + badge status --}}
        <div class="flex items-start justify-between mb-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="text-lg font-bold text-slate-100" x-text="p.ticker"></h3>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase bg-slate-800 text-slate-400 border border-slate-700"
                    x-text="p.strategy_label"></span>
            </div>
            <p class="text-[11px] text-slate-500 mt-0.5" x-text="p.stock_name"></p>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap"
                :class="{
                  'bg-rose-500/20 text-rose-400': p.status === 'danger',
                  'bg-amber-500/20 text-amber-400': p.status === 'warning',
                  'bg-green-500/20 text-green-400': p.status === 'safe',
                  'bg-slate-700 text-slate-400': p.status === 'unknown',
                }"
                x-text="{
                  danger: '🔴 BAHAYA',
                  warning: '🟡 WASPADA',
                  safe: '🟢 AMAN',
                  unknown: '⚪ N/A',
                }[p.status]"></span>
        </div>

        {{-- Harga: entry vs sekarang + PnL --}}
        <div class="grid grid-cols-3 gap-2 mb-3 text-sm">
          <div>
            <p class="text-[10px] text-slate-500 uppercase">Entry</p>
            <p class="font-mono text-slate-300" x-text="fmtRp(p.entry_price)"></p>
          </div>
          <div>
            <p class="text-[10px] text-slate-500 uppercase">Sekarang</p>
            <p class="font-mono font-semibold" x-text="p.current_price ? fmtRp(p.current_price) : '—'"></p>
          </div>
          <div>
            <p class="text-[10px] text-slate-500 uppercase">Floating PnL</p>
            <p class="font-mono font-semibold"
               :class="(p.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-rose-400'"
               x-text="p.pnl !== null ? ((p.pnl >= 0 ? '+' : '') + 'Rp' + Math.round(p.pnl).toLocaleString('id-ID')) : '—'"></p>
            <p class="text-[10px]" :class="(p.pnl_percent ?? 0) >= 0 ? 'text-green-400/70' : 'text-rose-400/70'"
               x-text="p.pnl_percent !== null ? ((p.pnl_percent >= 0 ? '+' : '') + p.pnl_percent.toFixed(2) + '%') : ''"></p>
          </div>
        </div>

        {{-- Bar jarak ke trailing stop --}}
        <div class="mb-3">
          <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
            <span>Jarak ke Trailing Stop (Rp<span x-text="fmtNum(p.trailing_sl)"></span>)</span>
            <span class="font-mono font-semibold"
                  :class="{
                    'text-rose-400': p.status === 'danger',
                    'text-amber-400': p.status === 'warning',
                    'text-green-400': p.status === 'safe',
                  }"
                  x-text="p.distance_to_sl_pct !== null ? (p.distance_to_sl_pct >= 0 ? '+' : '') + p.distance_to_sl_pct.toFixed(2) + '%' : '—'"></span>
          </div>
          <div class="h-2 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full transition-all"
                 :class="{
                   'bg-rose-500': p.status === 'danger',
                   'bg-amber-500': p.status === 'warning',
                   'bg-green-500': p.status === 'safe',
                   'bg-slate-600': p.status === 'unknown',
                 }"
                 :style="'width: ' + slBarWidth(p) + '%'"></div>
          </div>
          <p class="text-[10px] text-slate-600 mt-1">Puncak sejak entry: Rp<span x-text="fmtNum(p.peak_since_entry)"></span></p>
        </div>

        {{-- Sisa hari ke target waktu --}}
        <div class="flex items-center justify-between text-[11px] pt-2 border-t border-slate-800/60">
          <span class="text-slate-500">
            Hari bursa ke-<span x-text="p.trading_days_held" class="text-slate-300 font-semibold"></span> / 10
          </span>
          <span :class="p.time_target_overdue ? 'text-orange-400 font-semibold' : 'text-slate-400'"
                x-text="p.time_target_overdue
                  ? '⏰ Target waktu terlewat ' + Math.abs(p.days_remaining_to_target) + ' hari -- pertimbangkan tutup'
                  : 'Sisa ' + p.days_remaining_to_target + ' hari bursa'"></span>
        </div>
      </div>
    </template>
  </div>
</div>
</x-app-layout>
