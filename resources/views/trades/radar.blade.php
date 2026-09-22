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
    <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <a href="{{ route('trades.live') }}"
         class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition inline-flex items-center gap-1 font-medium"
         title="Live Trailing Stop Monitor">
        <x-heroicon-o-bolt class="w-3.5 h-3.5 text-amber-400" /> Live Monitor
      </a>
      <a href="{{ route('trades.index') }}"
         class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition inline-flex items-center gap-1 font-medium"
         title="Trade Journal">
        <x-heroicon-o-book-open class="w-3.5 h-3.5 text-slate-400" /> Journal
      </a>
      <a href="{{ route('trades.radar-log') }}"
         class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition inline-flex items-center gap-1 font-medium"
         title="Radar Log">
        <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
        </svg>
        Log
      </a>
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
  {{-- ── SEKSI SELF_RADAR_V1 ── --}}
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1 flex items-center gap-2">
      <x-heroicon-o-bolt class="w-4 h-4 text-emerald-400" /> SELF_RADAR_V1 <span class="text-[10px] text-emerald-400 font-normal normal-case">(experimental fallback: RSI14 ≥ 60, ret_5d ≥ 5%, dd_20d ≥ -5%)</span>
    </h2>
    <p class="text-[11px] text-slate-500 mb-3">Overnight continuation: tanggal entry dan mulai trailing stop ditulis di tiap kartu. Bukan sinyal resmi.</p>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
      <template x-for="row in radar.self_radar || []" :key="row.ticker + '-selfradar'">
        <div class="glass-card rounded-2xl p-4 border-2 transition-colors"
             :class="row.triggered ? 'border-emerald-500/50 bg-emerald-500/[0.05]' : 'border-slate-800/80'">
          <div class="flex items-center justify-between mb-2">
            <span class="font-bold text-slate-100" x-text="row.ticker"></span>
            <span class="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  :class="row.triggered ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-700 text-slate-400 border border-slate-600'"
                  x-text="row.status"></span>
          </div>
          <p class="text-lg font-mono font-bold text-slate-100 mb-2" x-text="'Rp' + fmtNum(row.price_now, 0)"></p>
          <div class="space-y-1.5 text-[11px]">
            <div class="flex justify-between"><span class="text-slate-500">RSI14</span><span class="font-mono" :class="row.rsi14_now >= 60 ? 'text-emerald-400' : 'text-slate-300'" x-text="fmtNum(row.rsi14_now)"></span></div>
            <div class="flex justify-between"><span class="text-slate-500">ret_5d</span><span class="font-mono" :class="row.ret_5d_pct >= 5 ? 'text-emerald-400' : 'text-slate-300'" x-text="fmtNum(row.ret_5d_pct) + '%'"></span></div>
            <div class="flex justify-between"><span class="text-slate-500">dd_20d</span><span class="font-mono" :class="row.dd_20d_pct >= -5 ? 'text-emerald-400' : 'text-slate-300'" x-text="fmtNum(row.dd_20d_pct) + '%'"></span></div>
          </div>
          <p class="text-[10px] text-slate-500 mt-3" x-text="row.entry_plan"></p>
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

  {{-- ── SEKSI TINS BOTTOM-TO-TOP SWING (SPECIAL RADAR) ── --}}
  <div x-show="radar.tins_bottom_to_top" x-cloak>
    <div class="flex flex-wrap items-center justify-between gap-2 mb-1">
      <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
        <x-heroicon-o-chart-bar-square class="w-4 h-4 text-cyan-400" /> TINS BOTTOM-TO-TOP SWING
        <span class="text-[10px] text-cyan-400 font-normal normal-case">(Ambil di Dasar Diskon &times; Jual di Pucuk Reli)</span>
      </h2>
      <span class="text-[10px] px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 font-medium">
        Backtest Terbukti: WR 66.7% (+84.66%)
      </span>
    </div>
    <p class="text-[11px] text-slate-500 mb-3">
      Radar siklus khusus TINS: deteksi titik diskon ekstrem (Stoch &lt; 30 / BB %B &lt; 0.25 / RSI &lt; 45) terkonfirmasi lilin hijau. Auto SL -3.0%, trailing lock 2.5%.
    </p>

    <div class="glass-card rounded-2xl p-5 border-2 transition-colors max-w-2xl"
         :class="radar.tins_bottom_to_top?.triggered ? 'border-emerald-500/60 bg-emerald-500/[0.06] ring-2 ring-emerald-500/20' : (radar.tins_bottom_to_top?.status?.includes('OVERBOUGHT') ? 'border-amber-500/40 bg-amber-500/[0.02]' : 'border-slate-800/80')">
      
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div class="flex items-center gap-2">
          <span class="text-lg font-bold text-slate-100 tracking-wide">TINS</span>
          <span class="text-xs text-slate-400 font-mono">PT Timah Tbk</span>
        </div>
        <div>
          <span class="text-[11px] px-2.5 py-1 rounded-full font-bold inline-flex items-center gap-1.5"
                :class="radar.tins_bottom_to_top?.triggered 
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 shadow-sm shadow-emerald-500/20' 
                          : (radar.tins_bottom_to_top?.status?.includes('DISKON') 
                              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40' 
                              : (radar.tins_bottom_to_top?.status?.includes('OVERBOUGHT')
                                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                  : 'bg-slate-700 text-slate-400 border border-slate-600'))">
            <span class="w-2 h-2 rounded-full"
                  :class="radar.tins_bottom_to_top?.triggered ? 'bg-emerald-400 animate-ping' : (radar.tins_bottom_to_top?.status?.includes('DISKON') ? 'bg-sky-400' : (radar.tins_bottom_to_top?.status?.includes('OVERBOUGHT') ? 'bg-amber-400' : 'bg-slate-500'))"></span>
            <span x-text="radar.tins_bottom_to_top?.status"></span>
          </span>
        </div>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 py-3 border-y border-slate-800/60 my-2">
        <div>
          <span class="text-[10px] text-slate-500 block uppercase">Harga Live</span>
          <span class="text-lg font-mono font-bold text-slate-100" x-text="'Rp' + fmtNum(radar.tins_bottom_to_top?.price_now, 0)"></span>
        </div>
        <div>
          <span class="text-[10px] text-slate-500 block uppercase">Lilin Hari Ini</span>
          <span class="text-xs font-semibold inline-flex items-center gap-1 mt-1"
                :class="radar.tins_bottom_to_top?.is_green ? 'text-emerald-400' : 'text-rose-400'">
            <span x-text="radar.tins_bottom_to_top?.is_green ? 'HIJAU (Konfirmasi)' : 'MERAH / NETRAL'"></span>
          </span>
        </div>
        <div>
          <span class="text-[10px] text-slate-500 block uppercase">Stop Loss Ketat</span>
          <span class="text-xs font-mono font-bold text-rose-400 mt-1 block" x-text="'Rp' + fmtNum(radar.tins_bottom_to_top?.sl_price, 0) + ' (-3%)'"></span>
        </div>
        <div>
          <span class="text-[10px] text-slate-500 block uppercase">Trailing Profit</span>
          <span class="text-xs font-mono font-bold text-emerald-400 mt-1 block">2.5% dari Puncak</span>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] mt-3">
        <div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800">
          <div class="flex justify-between">
            <span class="text-slate-400">Stochastic %K</span>
            <span class="font-mono font-bold"
                  :class="radar.tins_bottom_to_top?.stoch_k < 30 ? 'text-emerald-400' : (radar.tins_bottom_to_top?.stoch_k > 75 ? 'text-amber-400' : 'text-slate-200')"
                  x-text="fmtNum(radar.tins_bottom_to_top?.stoch_k, 1) + ' (Ambang < 30)'"></span>
          </div>
        </div>
        <div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800">
          <div class="flex justify-between">
            <span class="text-slate-400">BB %B</span>
            <span class="font-mono font-bold"
                  :class="radar.tins_bottom_to_top?.bb_pct_b < 0.25 ? 'text-emerald-400' : (radar.tins_bottom_to_top?.bb_pct_b > 0.85 ? 'text-amber-400' : 'text-slate-200')"
                  x-text="fmtNum(radar.tins_bottom_to_top?.bb_pct_b, 2) + ' (Ambang < 0.25)'"></span>
          </div>
        </div>
        <div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800">
          <div class="flex justify-between">
            <span class="text-slate-400">RSI(14)</span>
            <span class="font-mono font-bold"
                  :class="radar.tins_bottom_to_top?.rsi14 < 45 ? 'text-emerald-400' : (radar.tins_bottom_to_top?.rsi14 > 65 ? 'text-amber-400' : 'text-slate-200')"
                  x-text="fmtNum(radar.tins_bottom_to_top?.rsi14, 1) + ' (Ambang < 45)'"></span>
          </div>
        </div>
      </div>

      <div class="mt-3 text-[10px] text-slate-500 bg-slate-950/40 rounded-lg p-2.5 border border-slate-800/60" x-text="radar.tins_bottom_to_top?.notes"></div>
    </div>
  </div>

  {{-- ── SEKSI RADAR BSJP MOMENTUM (BELI SORE JUAL PAGI) ── --}}
  <div x-show="radar.bsjp_momentum" x-cloak class="space-y-3 pt-2">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-1">
      <div>
        <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
          <x-heroicon-o-bolt class="w-4 h-4 text-amber-400" /> RADAR BSJP MOMENTUM (BELI SORE JUAL PAGI)
          <span class="text-[10px] text-amber-300 font-normal normal-case">(Skema 2-Tahap: 15:00 Early Warning &rarr; 15:35 Final Call)</span>
        </h2>
        <p class="text-[11px] text-slate-500 mt-0.5">
          Deteksi lonjakan volume & lilin hijau solid menjelang penutupan sesi 2. Beli di Pre-Closing (15:50 WIB) &times; Take Profit di Open (09:00 WIB).
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] px-2.5 py-1 rounded-full font-semibold border flex items-center gap-1.5"
              :class="radar.bsjp_momentum?.stage === 'confirm' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-amber-500/20 text-amber-300 border-amber-500/40'">
          <span class="w-1.5 h-1.5 rounded-full" :class="radar.bsjp_momentum?.stage === 'confirm' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'"></span>
          <span x-text="radar.bsjp_momentum?.stage_label"></span>
        </span>
        <span class="text-[10px] px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-medium">
          Backtest: +453.83% (WR 50% | H+1 High 82.8%)
        </span>
        <a href="{{ route('trades.bsjp-tracker') }}"
           class="text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 transition flex items-center gap-1 font-semibold">
          <x-heroicon-o-bolt class="w-3.5 h-3.5 text-amber-400" />
          Live Tracker (Rp 20 Jt) &rarr;
        </a>
      </div>
    </div>

    {{-- Filter Tabs (All / Rocket / Sweetspot) --}}
    <div class="flex flex-wrap items-center gap-2 pt-1 pb-1">
      <button type="button" @click="bsjpCategory = 'all'"
              class="px-2.5 py-1 rounded-lg text-xs font-medium transition"
              :class="bsjpCategory === 'all' ? 'bg-slate-700 text-slate-100 border border-slate-600' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'">
        Semua (<span x-text="(radar.bsjp_momentum?.candidates || []).length"></span>)
      </button>
      <button type="button" @click="bsjpCategory = 'rocket'"
              class="px-2.5 py-1 rounded-lg text-xs font-medium transition inline-flex items-center gap-1.5"
              :class="bsjpCategory === 'rocket' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'">
        <span>🚀 Super Rocket (&ge;15%)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded-full bg-rose-500/30 text-rose-200 font-mono"
              x-text="(radar.bsjp_momentum?.candidates || []).filter(c => c.category === 'rocket').length"></span>
      </button>
      <button type="button" @click="bsjpCategory = 'sweetspot'"
              class="px-2.5 py-1 rounded-lg text-xs font-medium transition inline-flex items-center gap-1.5"
              :class="bsjpCategory === 'sweetspot' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'">
        <span>🎯 Sweetspot BSJP (4% - 15%)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded-full bg-emerald-500/30 text-emerald-200 font-mono"
              x-text="(radar.bsjp_momentum?.candidates || []).filter(c => c.category === 'sweetspot').length"></span>
      </button>
    </div>

    {{-- Cards Grid --}}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
      <template x-for="item in filteredBsjpCandidates()" :key="item.ticker + '-bsjp'">
        <div class="glass-card rounded-2xl p-4 border-2 transition-all hover:border-slate-700"
             :class="radar.bsjp_momentum?.stage === 'confirm' ? 'border-emerald-500/40 bg-emerald-500/[0.03]' : 'border-slate-800/80 bg-slate-900/40'">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="font-bold text-base text-slate-100" x-text="item.ticker"></span>
              <span class="text-[11px] font-semibold text-emerald-400" x-text="'+' + fmtNum(item.return_pct, 2) + '%'"></span>
              <span class="text-[9px] px-2 py-0.5 rounded-full border font-semibold inline-flex items-center gap-1"
                    :class="item.category_badge || (item.category === 'rocket' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30')"
                    x-text="item.category_label || (item.category === 'rocket' ? '🚀 Super Rocket' : '🎯 Sweetspot')"></span>
            </div>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 font-bold font-mono"
                  x-text="'Vol ' + item.volume_ratio + 'x'"></span>
          </div>

          <p class="text-xs text-slate-400 truncate mb-3" x-text="item.name"></p>

          <div class="grid grid-cols-2 gap-2 py-2 border-y border-slate-800/80 text-[11px] mb-3">
            <div>
              <span class="text-slate-500 block text-[10px]">Harga Sore</span>
              <span class="font-mono font-bold text-slate-200" x-text="'Rp' + fmtNum(item.price, 0)"></span>
            </div>
            <div>
              <span class="text-slate-500 block text-[10px]">Nilai Trx</span>
              <span class="font-mono font-bold text-slate-300" x-text="'Rp' + fmtNum(item.value / 1000000000, 2) + ' M'"></span>
            </div>
            <div>
              <span class="text-slate-500 block text-[10px]">Target Jual (09:00 WIB)</span>
              <span class="font-mono font-bold text-emerald-400" x-text="'Rp' + fmtNum(item.target_tp, 0) + ' (+2.5%)'"></span>
            </div>
            <div>
              <span class="text-slate-500 block text-[10px]">Stop Loss</span>
              <span class="font-mono font-bold text-rose-400" x-text="'Rp' + fmtNum(item.stop_loss, 0) + ' (-3%)'"></span>
            </div>
          </div>

          <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 pb-2">
            <span class="inline-flex items-center gap-1">
              <x-heroicon-o-clock class="w-3.5 h-3.5 text-slate-500" /> Beli: Pre-Closing (15:50 WIB)
            </span>
            <span class="text-emerald-400 font-medium">Jual: Open Besok</span>
          </div>

          {{-- Quick Action Button --}}
          <div class="pt-2 border-t border-slate-800/80">
            <form action="{{ route('trades.bsjp-tracker.buy') }}" method="POST">
              @csrf
              <input type="hidden" name="ticker" :value="item.ticker">
              <input type="hidden" name="signal_date" :value="radar.bsjp_momentum?.trade_date || ''">
              <input type="hidden" name="entry_price" :value="item.price">
              <input type="hidden" name="category" :value="item.category">
              <input type="hidden" name="target_tp" :value="item.target_tp">
              <input type="hidden" name="stop_loss" :value="item.stop_loss">
              <input type="hidden" name="capital" value="20000000">
              <button type="submit"
                      class="w-full py-1.5 px-3 rounded-xl bg-emerald-600/90 hover:bg-emerald-500 text-white font-bold text-xs shadow-md shadow-emerald-600/20 transition flex items-center justify-center gap-1.5">
                <x-heroicon-o-shopping-cart class="w-3.5 h-3.5" />
                Catat Beli Rp 20 Jt
              </button>
            </form>
          </div>
        </div>
      </template>
    </div>
  </div>

</div>
</x-app-layout>
