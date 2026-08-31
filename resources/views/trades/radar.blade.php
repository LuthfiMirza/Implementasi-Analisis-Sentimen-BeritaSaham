<x-app-layout>
<div class="space-y-6" x-data="signalRadarMonitor(@js($radar))">

  {{-- ── HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5 flex items-center gap-2">
        <x-heroicon-o-signal class="w-6 h-6" /> Signal Radar
        <span class="relative flex h-2.5 w-2.5">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-sky-500"></span>
        </span>
      </h1>
      <p class="text-sm text-slate-400 mt-1">
        Ticker mana yang mendekati threshold sinyal -- auto-refresh tiap 45 detik.
      </p>
    </div>
    <div class="flex items-center gap-2 text-xs text-slate-500">
      <span x-show="loading" x-cloak class="text-sky-400">Memuat...</span>
      <span>Estimasi per: <span x-text="radar.generated_at || '—'" class="text-slate-300 font-mono"></span> WIB</span>
      <button type="button" @click="fetchData()"
              class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition"
              title="Refresh sekarang">
        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
      </button>
    </div>
  </div>

  {{-- ── DISCLAIMER (WAJIB, jangan dihapus/dilemahkan) ── --}}
  <div class="glass-card border border-amber-500/30 bg-amber-500/[0.04] rounded-2xl p-4">
    <p class="text-sm text-amber-300 font-medium flex items-start gap-2">
      <x-heroicon-o-exclamation-triangle class="w-4 h-4 shrink-0 mt-0.5" />
      <span>
        Ini <strong>ESTIMASI LIVE</strong>, bukan sinyal resmi. Dihitung pakai harga BERJALAN
        sebagai hipotetis closing hari ini -- bisa berubah kapan saja sampai closing final
        <strong>15:15 WIB</strong>. Sinyal resmi (yang benar-benar masuk Trade Journal + kirim
        Telegram) cuma lahir dari <code class="text-amber-200">research:detect-drawdown-bounce-signal</code>
        jam <strong>15:18 WIB</strong>. Jangan jadikan angka di halaman ini sebagai instruksi beli.
      </span>
    </p>
  </div>

  {{-- ── SEKSI GABUNGAN ── --}}
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1 flex items-center gap-2">
      <x-heroicon-o-arrow-trending-down class="w-4 h-4 text-rose-400" /> GABUNGAN <span class="text-[10px] text-slate-500 font-normal normal-case">(ret_2d &le; -5% atau drawdown_20d &le; -20%)</span>
    </h2>
    <p class="text-[11px] text-slate-500 mb-3">Mean-reversion: beli saat harga sudah jatuh, taruhan rebound.</p>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      <template x-for="row in radar.gabungan" :key="row.ticker + '-gabungan'">
        <div class="glass-card rounded-2xl p-4 border-2 transition-colors"
             :class="row.triggered ? 'border-rose-500/50 bg-rose-500/[0.05]' : 'border-slate-800/80'">
          <div class="flex items-center justify-between mb-2">
            <span class="font-bold text-slate-100" x-text="row.ticker"></span>
            <span x-show="row.triggered" class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold inline-flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> SUDAH LEWAT THRESHOLD
            </span>
          </div>
          <p class="text-lg font-mono font-bold text-slate-100 mb-2" x-text="'Rp' + fmtNum(row.price_now, 0)"></p>

          <div class="space-y-2">
            <div>
              <div class="flex justify-between text-[11px] mb-1">
                <span class="text-slate-500">ret_2d</span>
                <span class="font-mono" :class="row.ret_2d_pct <= -5 ? 'text-rose-400' : 'text-slate-300'"
                      x-text="fmtNum(row.ret_2d_pct) + '% (ambang -5%)'"></span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div class="h-full rounded-full transition-all"
                     :class="row.ret_2d_distance_pp <= 0 ? 'bg-rose-500' : 'bg-sky-500'"
                     :style="`width: ${barWidth(row.ret_2d_distance_pp, 5)}%`"></div>
              </div>
            </div>
            <template x-if="row.dd_20d_distance_pp !== null">
              <div>
                <div class="flex justify-between text-[11px] mb-1">
                  <span class="text-slate-500">drawdown_20d</span>
                  <span class="font-mono" :class="row.dd_20d_pct <= -20 ? 'text-rose-400' : 'text-slate-300'"
                        x-text="fmtNum(row.dd_20d_pct) + '% (ambang -20%)'"></span>
                </div>
                <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div class="h-full rounded-full transition-all"
                       :class="row.dd_20d_distance_pp <= 0 ? 'bg-rose-500' : 'bg-sky-500'"
                       :style="`width: ${barWidth(row.dd_20d_distance_pp, 20)}%`"></div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>
  </div>

  {{-- ── SEKSI MOMENTUM ── --}}
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1 flex items-center gap-2">
      <x-heroicon-o-arrow-trending-up class="w-4 h-4 text-amber-400" /> MOMENTUM <span class="text-[10px] text-amber-400 font-normal normal-case">(RSI14 &gt; 60 -- EXPLORATORY, regime-dependent)</span>
    </h2>
    <p class="text-[11px] text-slate-500 mb-3">Trend-following: beli saat momentum sudah naik kencang.</p>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
      <template x-for="row in radar.momentum" :key="row.ticker + '-momentum'">
        <div class="glass-card rounded-2xl p-4 border-2 transition-colors"
             :class="row.triggered ? 'border-rose-500/50 bg-rose-500/[0.05]' : 'border-slate-800/80'">
          <div class="flex items-center justify-between mb-2">
            <span class="font-bold text-slate-100" x-text="row.ticker"></span>
            <span x-show="row.triggered" class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold inline-flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> SUDAH LEWAT
            </span>
          </div>
          <p class="text-lg font-mono font-bold text-slate-100 mb-2" x-text="'Rp' + fmtNum(row.price_now, 0)"></p>
          <div class="flex justify-between text-[11px] mb-1">
            <span class="text-slate-500">RSI14</span>
            <span class="font-mono" :class="row.rsi14_now > 60 ? 'text-rose-400' : 'text-slate-300'"
                  x-text="fmtNum(row.rsi14_now) + ' (ambang 60)'"></span>
          </div>
          <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full transition-all"
                 :class="row.distance_pp <= 0 ? 'bg-rose-500' : 'bg-sky-500'"
                 :style="`width: ${barWidth(row.distance_pp, 15)}%`"></div>
          </div>
        </div>
      </template>
    </div>
  </div>

  {{-- ── SEKSI BOTTOM_REBOUND ── --}}
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1 flex items-center gap-2">
      <x-heroicon-o-arrow-uturn-up class="w-4 h-4 text-sky-400" /> BOTTOM_REBOUND <span class="text-[10px] text-slate-500 font-normal normal-case">(cross pertama &gt; bottom_10d &times; 1,05)</span>
    </h2>
    <p class="text-[11px] text-slate-500 mb-3">Tunggu titik bawah 10 hari terkonfirmasi rebound, baru masuk.</p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <template x-for="row in radar.bottom_rebound" :key="row.ticker + '-bottomrebound'">
        <div class="glass-card rounded-2xl p-4 border-2 transition-colors"
             :class="row.triggered_today ? 'border-rose-500/50 bg-rose-500/[0.05]' : 'border-slate-800/80'">
          <div class="flex items-center justify-between mb-2">
            <span class="font-bold text-slate-100" x-text="row.ticker"></span>
            <span x-show="row.triggered_today" class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold inline-flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> CROSS BARU HARI INI
            </span>
            <span x-show="!row.triggered_today && row.already_in_zone" class="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-400 border border-slate-600 font-semibold">
              sudah di atas ambang (bukan sinyal baru)
            </span>
          </div>
          <p class="text-lg font-mono font-bold text-slate-100 mb-2" x-text="'Rp' + fmtNum(row.price_now, 0)"></p>
          <div class="flex justify-between text-[11px] mb-1">
            <span class="text-slate-500">Threshold (bottom_10d kemarin &times; 1,05)</span>
            <span class="font-mono text-slate-300" x-text="'Rp' + fmtNum(row.threshold_price, 0)"></span>
          </div>
          <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full transition-all"
                 :class="row.distance_pct >= 0 ? 'bg-rose-500' : 'bg-sky-500'"
                 :style="`width: ${barWidth(-row.distance_pct, 5)}%`"></div>
          </div>
          <p class="text-[11px] text-slate-500 mt-1" x-text="'Jarak: ' + fmtNum(row.distance_pct) + '%'"></p>
        </div>
      </template>
    </div>
  </div>

</div>
</x-app-layout>
