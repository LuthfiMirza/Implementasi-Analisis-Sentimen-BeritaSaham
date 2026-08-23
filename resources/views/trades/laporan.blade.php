<x-app-layout>
<div class="space-y-6">

  {{-- ── HEADER ── --}}
  {{-- Bug SAMA seperti toggle Rupiah/vs IHSG di bawah (ditemukan bareng, akar sebabnya sama):
       tanpa flex-wrap, blok judul kiri tidak menyusut dan mendorong toggle GABUNGAN/Semua
       Strategi keluar layar di viewport sempit. Sudah ada sejak Fase CL, baru ketahuan sekarang. --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <a href="{{ route('trades.index') }}"
         class="text-[11px] text-slate-500 hover:text-slate-300 transition inline-flex items-center gap-1 mb-1">
        ← Kembali ke Trade Journal
      </a>
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5">Laporan Trade</h1>
      <p class="text-sm text-slate-400 mt-1">Statistik lengkap, episode independensi, dan riwayat penuh</p>
      {{-- Fase CA: dulu kartu ringkasan mencampur GABUNGAN + 2 aturan lama yang TERBUKTI
           tumpang tindih periode untuk saham sama (dicek dari notes backfill sendiri) --
           sekarang cuma GABUNGAN yang resmi, sisanya di bagian "Strategi Lain" di bawah. --}}
      <p class="text-[11px] text-sky-400/80 mt-1">
        @if($scope === 'all')
          📊 Kartu di bawah = <b>SEMUA strategi digabung</b> (termasuk yang overlap/pensiun)
        @else
          📊 Kartu di bawah = <b>strategi resmi GABUNGAN</b> saja (ret_2d≤-5% atau drawdown≤-20%)
        @endif
      </p>
    </div>
    {{-- Fase CL: toggle GABUNGAN (resmi) vs SEMUA strategi -- link biasa (bukan JS), state
         murni dari query string ?scope=, jadi bisa di-bookmark/share dan tetap benar kalau
         halaman di-refresh. --}}
    <div class="inline-flex rounded-xl border border-slate-800 bg-slate-900/60 p-1 text-xs shrink-0">
      <a href="{{ route('trades.laporan') }}"
         class="px-3 py-1.5 rounded-lg font-medium transition
                {{ $scope === 'gabungan' ? 'bg-sky-500 text-slate-900' : 'text-slate-400 hover:text-slate-200' }}">
        GABUNGAN (resmi)
      </a>
      <a href="{{ route('trades.laporan', ['scope' => 'all']) }}"
         class="px-3 py-1.5 rounded-lg font-medium transition
                {{ $scope === 'all' ? 'bg-amber-500 text-slate-900' : 'text-slate-400 hover:text-slate-200' }}">
        Semua Strategi
      </a>
    </div>
  </div>

  {{-- ── LAPORAN PORTOFOLIO ala StockBit (Fase CU rework Fase CX) ── --}}
  {{-- Fase CX: sekarang IKUT toggle scope (GABUNGAN vs Semua Strategi) -- dikonfirmasi user via
       AskUserQuestion (2026-08-23). Sebelumnya (Fase CU) selalu GABUNGAN, tapi user minta bisa
       switch supaya bisa lihat performa gabungan semua strategi juga di section ini. --}}

  {{-- BARIS 1: 3-kolom StockBit -- Total Equity | Total Equity Return | Portfolio Allocation --}}
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">

    {{-- ═══ TOTAL EQUITY (kartu kiri atas + mini chart) ═══ --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-5">
      <div class="flex items-start justify-between mb-3">
        <div>
          <p class="text-[10px] text-slate-500 uppercase font-medium">Total Equity ({{ $portfolioReport['scope_label'] }})</p>
          <p class="text-2xl font-bold text-slate-100 font-mono mt-1">
            @php
              $lastEquity = !empty($portfolioReport['daily_equity_table']) ? $portfolioReport['daily_equity_table'][0]['equity'] : 0;
            @endphp
            Rp{{ number_format($lastEquity, 0, ',', '.') }}
          </p>
          <p class="text-[10px] text-slate-500 mt-1" title="Sistem non-compounding: Modal Dikerahkan (n_trade × Rp10jt LIVE_CAPITAL) + PnL Kumulatif realisasi. Bukan compounding fiktif dari Rp10jt awal.">
            = Modal Dikerahkan + PnL Kumulatif (non-compounding)
          </p>
        </div>
      </div>
      @if(empty($portfolioReport['chart']['labels']))
        <div class="h-32 flex items-center justify-center text-xs text-slate-500">Belum ada trade closed.</div>
      @else
        <div class="relative h-32 w-full overflow-hidden">
          <canvas x-data="equityChart(@js($portfolioReport['chart']))" x-ref="canvas" class="!w-full"></canvas>
        </div>
      @endif
    </div>

    {{-- ═══ TOTAL EQUITY RETURN (tabel harian, tengah) ═══ --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-5">
      <div class="flex items-center justify-between mb-3">
        <p class="text-[10px] text-slate-500 uppercase font-medium">Total Equity Return</p>
        <span class="text-[10px] text-slate-500 italic">Last 30 aktivitas</span>
      </div>
      @if(empty($portfolioReport['daily_equity_table']))
        <div class="h-32 flex items-center justify-center text-xs text-slate-500">Belum ada trade closed.</div>
      @else
        <div class="overflow-y-auto max-h-64 -mx-2 px-2">
          <table class="w-full text-xs">
            <thead class="sticky top-0 bg-slate-900/95 backdrop-blur">
              <tr class="text-left text-[10px] text-slate-500 uppercase border-b border-slate-800">
                <th class="py-1.5 pr-2">Date</th>
                <th class="py-1.5 pr-2 text-right">Equity</th>
                <th class="py-1.5 text-right">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              @foreach($portfolioReport['daily_equity_table'] as $row)
              <tr class="border-b border-slate-800/40">
                <td class="py-1 pr-2 text-slate-400 font-mono">{{ \Carbon\Carbon::parse($row['date'])->format('d M y') }}</td>
                <td class="py-1 pr-2 text-right font-mono text-slate-200">{{ number_format($row['equity'], 0, ',', '.') }}</td>
                <td class="py-1 text-right font-mono {{ $row['pnl'] > 0 ? 'text-green-400' : ($row['pnl'] < 0 ? 'text-rose-400' : 'text-slate-500') }}">
                  {{ $row['pnl'] > 0 ? '+' : '' }}{{ number_format($row['pnl'], 0, ',', '.') }}
                  <span class="text-[9px] opacity-70">({{ $row['pnl_pct'] > 0 ? '+' : '' }}{{ $row['pnl_pct'] }}%)</span>
                </td>
              </tr>
              @endforeach
            </tbody>
          </table>
        </div>
      @endif
    </div>

    {{-- ═══ PORTFOLIO ALLOCATION (donut kanan) ═══ --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-5">
      <div class="flex items-center justify-between mb-3">
        <p class="text-[10px] text-slate-500 uppercase font-medium">Portfolio Allocation</p>
        <span class="text-[10px] text-slate-500 italic">Posisi terbuka</span>
      </div>
      @if(empty($portfolioReport['allocation']))
        <div class="h-40 flex items-center justify-center text-xs text-slate-500 text-center px-4">
          Tidak ada posisi terbuka di scope {{ $portfolioReport['scope_label'] }}.
        </div>
      @else
        <div class="flex flex-col items-center">
          <div class="relative w-40 h-40" x-data="allocationDonut(@js($portfolioReport['allocation']))">
            <canvas x-ref="canvas" class="!w-full !h-full"></canvas>
            <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <p class="text-[9px] text-slate-500 uppercase">Total</p>
              <p class="text-sm font-bold font-mono text-slate-100">Rp{{ number_format($portfolioReport['allocation_total'], 0, ',', '.') }}</p>
              <p class="text-[9px] text-slate-500 mt-0.5">{{ count($portfolioReport['allocation']) }} saham</p>
            </div>
          </div>
          <div class="w-full mt-4 space-y-1.5">
            @foreach($portfolioReport['allocation'] as $a)
            <div class="flex items-center justify-between text-xs">
              <span class="font-semibold text-slate-200">{{ $a['ticker'] }} <span class="text-[10px] text-slate-500 font-normal">({{ $a['positions'] }} pos)</span></span>
              <span class="font-mono text-slate-400">Rp{{ number_format($a['value'], 0, ',', '.') }} <span class="text-slate-500">· {{ $a['pct'] }}%</span></span>
            </div>
            @endforeach
          </div>
        </div>
      @endif
    </div>
  </div>

  {{-- BARIS 2: Cumulative Portfolio Return chart (Rupiah/vs IHSG toggle) -- yang sudah ada, kena rework layout --}}
  <div class="glass-card border border-slate-800/80 rounded-2xl p-5" x-data="portfolioChart(@js($portfolioReport['chart']))">
    {{-- Fase CU bug (ditemukan user): tanpa flex-wrap, judul panjang "📈 Laporan Portofolio
         (GABUNGAN)" tidak menyusut (flex child default min-width:auto) dan mendorong toggle
         Rupiah/vs IHSG jauh keluar layar di viewport sempit (dicek: x=1116px di layar 375px lebar
         -- tombolnya ADA di DOM, cuma kegeser total ke luar area kelihatan). flex-wrap + min-w-0
         di judul supaya toggle turun ke baris baru alih-alih mendorong keluar. --}}
    <div class="flex flex-wrap items-center justify-between gap-2 mb-1">
      <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider min-w-0">📈 Cumulative Portfolio Return ({{ $portfolioReport['scope_label'] }})</h2>
      {{-- Toggle Rupiah vs vs-IHSG -- Alpine murni client-side, data 2 mode sudah sama-sama
           dikirim dari server, tidak perlu reload halaman. --}}
      <div class="inline-flex rounded-lg border border-slate-800 bg-slate-900/60 p-1 text-xs shrink-0">
        <button type="button" @click="mode = 'rp'"
                :class="mode === 'rp' ? 'bg-sky-500 text-slate-900' : 'text-slate-400 hover:text-slate-200'"
                class="px-3 py-1 rounded-md font-medium transition">Rupiah</button>
        <button type="button" @click="mode = 'ihsg'"
                :class="mode === 'ihsg' ? 'bg-sky-500 text-slate-900' : 'text-slate-400 hover:text-slate-200'"
                class="px-3 py-1 rounded-md font-medium transition">vs IHSG</button>
      </div>
    </div>
    <p class="text-[11px] text-slate-500 mb-3">
      <span x-show="mode === 'rp'">Total PnL kumulatif (Rp) direalisasi tiap posisi ditutup.</span>
      <span x-show="mode === 'ihsg'" x-cloak>Return % (basis modal Rp10jt/trade) vs IHSG, dinormalisasi 0% di trade pertama.</span>
    </p>

    @if(empty($portfolioReport['chart']['labels']))
      <div class="h-48 flex items-center justify-center text-sm text-slate-500">
        Belum ada trade GABUNGAN closed -- chart muncul setelah ada posisi yang direalisasi.
      </div>
    @else
      {{-- Bug ditemukan user (chart bikin seluruh halaman overflow horizontal, toggle Rupiah/vs
           IHSG kedorong keluar layar): kontainer canvas TIDAK punya `position: relative` --
           dokumentasi Chart.js eksplisit bilang ini WAJIB untuk `responsive: true` supaya
           ResizeObserver-nya bisa ukur ruang yang benar-benar tersedia. Tanpa itu, canvas bisa
           "kabur" ukurannya jauh lebih lebar dari kontainer aslinya. `w-full` + `overflow-hidden`
           di canvas sendiri sebagai pengaman tambahan. --}}
      <div class="relative h-56 md:h-64 w-full overflow-hidden">
        <canvas x-ref="canvas" class="!w-full"></canvas>
      </div>
    @endif

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Realized Gain</p>
        <p class="font-mono font-bold text-green-400 text-sm">+Rp{{ number_format($portfolioReport['realized_gain'], 0, ',', '.') }}</p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Realized Loss</p>
        <p class="font-mono font-bold text-rose-400 text-sm">-Rp{{ number_format($portfolioReport['realized_loss'], 0, ',', '.') }}</p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1"
           title="Total untung ÷ total rugi (absolut). >1 berarti untung total lebih besar dari rugi total.">Profit Factor</p>
        <p class="font-mono font-bold text-slate-100 text-sm">
          {{ $portfolioReport['profit_factor'] !== null ? number_format($portfolioReport['profit_factor'], 2) : '—' }}
        </p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Max Profit / Loss</p>
        <p class="font-mono text-[11px]">
          <span class="text-green-400">+Rp{{ number_format($portfolioReport['max_profit_trade']->pnl_total ?? 0, 0, ',', '.') }}</span>
          <span class="text-slate-600">/</span>
          <span class="text-rose-400">Rp{{ number_format($portfolioReport['max_loss_trade']->pnl_total ?? 0, 0, ',', '.') }}</span>
        </p>
      </div>
    </div>

    {{-- Fase CX: Trade Summary DETAIL ala StockBit -- Max/Avg Profit%, Total Transaction Value, Total Orders.
         Section terpisah dari 4 kartu di atas supaya tidak terlalu penuh di 1 baris di layar sempit. --}}
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Max Profit %</p>
        <p class="font-mono font-bold text-green-400 text-sm">
          {{ $portfolioReport['max_profit_pct'] !== null ? '+'.number_format($portfolioReport['max_profit_pct'], 2).'%' : '—' }}
        </p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Max Loss %</p>
        <p class="font-mono font-bold text-rose-400 text-sm">
          {{ $portfolioReport['max_loss_pct'] !== null ? number_format($portfolioReport['max_loss_pct'], 2).'%' : '—' }}
        </p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1">Avg Profit / Loss</p>
        <p class="font-mono text-[11px]">
          <span class="text-green-400">+Rp{{ number_format($portfolioReport['avg_profit'] ?? 0, 0, ',', '.') }}</span>
          <span class="text-slate-600">/</span>
          <span class="text-rose-400">Rp{{ number_format($portfolioReport['avg_loss'] ?? 0, 0, ',', '.') }}</span>
        </p>
      </div>
      <div class="bg-slate-900/60 rounded-xl p-3">
        <p class="text-[10px] text-slate-500 uppercase mb-1"
           title="Total nilai transaksi = jumlah semua position_value trade closed (bukan turnover intraday).">Total Transaction Value</p>
        <p class="font-mono font-bold text-slate-100 text-sm">
          Rp{{ number_format($portfolioReport['total_transaction_value'], 0, ',', '.') }}
        </p>
        <p class="text-[10px] text-slate-500 mt-0.5">{{ $portfolioReport['total_orders'] }} orders (buy+sell)</p>
      </div>
    </div>

    @if(!empty($portfolioReport['leaderboard']))
    <div class="mt-5">
      <p class="text-[11px] text-slate-500 uppercase font-medium mb-2">Top Gainer / Loser (Rp)</p>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-[10px] text-slate-500 uppercase border-b border-slate-800">
              <th class="py-2 pr-4">Saham</th>
              <th class="py-2 pr-4 text-right">Trade</th>
              <th class="py-2 text-right">P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            @foreach($portfolioReport['leaderboard'] as $row)
            <tr class="border-b border-slate-800/50">
              <td class="py-2 pr-4 font-semibold text-slate-200">{{ $row['ticker'] }}</td>
              <td class="py-2 pr-4 text-right text-slate-500">{{ $row['trades'] }}</td>
              <td class="py-2 text-right font-mono {{ $row['pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                {{ $row['pnl'] >= 0 ? '+' : '' }}Rp{{ number_format($row['pnl'], 0, ',', '.') }}
                <span class="text-[10px] text-slate-500">({{ $row['pnl_pct'] >= 0 ? '+' : '' }}{{ $row['pnl_pct'] }}%)</span>
              </td>
            </tr>
            @endforeach
          </tbody>
        </table>
      </div>
    </div>
    @endif
  </div>

  {{-- ── STATS CARDS ── --}}
  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">

    {{-- Total Trades --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Total Trade</p>
      <p class="text-2xl font-bold text-slate-100">{{ $stats['total'] }}</p>
      <p class="text-[11px] text-slate-500 mt-1">
        <span class="text-sky-400">{{ $stats['open'] }} open</span> •
        {{ $stats['closed'] }} closed
      </p>
    </div>

    {{-- Win Rate --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Win Rate</p>
      <p class="text-2xl font-bold
        {{ $stats['win_rate'] >= 60 ? 'text-green-400' :
           ($stats['win_rate'] >= 40 ? 'text-amber-400' : 'text-rose-400') }}">
        {{ $stats['win_rate'] }}%
      </p>
      <p class="text-[11px] mt-1">
        <span class="text-green-400">✓ {{ $stats['win'] }}W</span> •
        <span class="text-rose-400">✗ {{ $stats['loss'] }}L</span>
      </p>
      {{-- Trigger yang berdekatan (jeda <=15 hari, saham sama) digabung jadi 1 "episode" --
           tanpa ini, satu koreksi panjang bisa kelihatan seperti banyak trade independen padahal
           cuma 1 kejadian pasar. Lihat groupIntoEpisodes() di TradeController. --}}
      <p class="text-[10px] text-slate-500 mt-1.5 pt-1.5 border-t border-slate-800/60"
         title="Trigger berdekatan (jeda <=15 hari, saham sama) dianggap 1 kejadian pasar, bukan trade terpisah -- supaya tidak menggelembungkan jumlah 'kemenangan'.">
        ≈ <span class="text-slate-300 font-semibold">{{ $stats['episode_count'] }}</span> episode independen
        ({{ $stats['episode_win_rate'] }}% WR) — bukan {{ $stats['closed'] }} trade mentah
      </p>
    </div>

    {{-- Total PnL --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Total PnL</p>
      {{-- Angka Rupiah bisa panjang (9-12 digit) -- text-2xl tetap dipaksa muat di kartu sempit
           (grid-cols-2 di mobile) bikin "Rp" dan angka pecah baris. Font lebih kecil di layar
           sempit + whitespace-nowrap supaya selalu 1 baris, baru naik ke text-2xl di layar lebar
           (lg:grid-cols-6) yang kartu-nya lebih lega. --}}
      <p class="text-base sm:text-xl lg:text-2xl font-bold whitespace-nowrap
        {{ $stats['total_pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
        {{ $stats['total_pnl'] >= 0 ? '+' : '' }}Rp{{ number_format($stats['total_pnl'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Realized PnL</p>
    </div>

    {{-- Avg R:R --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Avg R:R</p>
      <p class="text-2xl font-bold
        {{ $stats['avg_rr'] >= 1.5 ? 'text-green-400' :
           ($stats['avg_rr'] >= 1 ? 'text-amber-400' : 'text-rose-400') }}">
        1:{{ $stats['avg_rr'] ?: '-' }}
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Actual achieved</p>
    </div>

    {{-- Expectancy --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Expectancy</p>
      <p class="text-2xl font-bold
        {{ $stats['expectancy'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
        {{ $stats['expectancy'] >= 0 ? '+' : '' }}{{ $stats['expectancy'] }}%
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Per trade avg</p>
    </div>

    {{-- Avg Holding --}}
    <div class="glass-card border border-slate-800/80 rounded-2xl p-4">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1">Avg Holding</p>
      <p class="text-2xl font-bold text-slate-100">{{ $stats['avg_holding'] ?: '-' }}</p>
      <p class="text-[11px] text-slate-500 mt-1">hari per trade</p>
    </div>

  </div>

  {{-- ── EPISODE INDEPENDEN PER BULAN (GABUNGAN resmi) ── --}}
  @if(!empty($monthlyBreakdown))
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
      📅 Episode Independen per Bulan
    </h2>
    <p class="text-[11px] text-slate-500 mb-3">
      Dikelompokkan berdasar bulan MULAI tiap episode (entry trade pertamanya) -- trigger
      berdekatan (jeda ≤15 hari, saham sama) dihitung 1 episode, bukan banyak trade terpisah.
    </p>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-[10px] text-slate-500 uppercase border-b border-slate-800">
            <th class="py-2 pr-4">Bulan</th>
            <th class="py-2 pr-4 text-right">Episode</th>
            <th class="py-2 pr-4 text-right">Trade Mentah</th>
            <th class="py-2 pr-4 text-right">Win Rate</th>
            <th class="py-2 text-right">Total PnL</th>
          </tr>
        </thead>
        <tbody>
          @foreach($monthlyBreakdown as $m)
          <tr class="border-b border-slate-800/50">
            <td class="py-2 pr-4 text-slate-200 font-medium">{{ $m['month_label'] }}</td>
            <td class="py-2 pr-4 text-right text-slate-200">{{ $m['episode_count'] }}</td>
            <td class="py-2 pr-4 text-right text-slate-500">{{ $m['trade_count'] }}</td>
            <td class="py-2 pr-4 text-right {{ $m['win_rate'] >= 60 ? 'text-green-400' : ($m['win_rate'] >= 40 ? 'text-amber-400' : 'text-rose-400') }}">
              {{ $m['win_rate'] }}%
            </td>
            <td class="py-2 text-right font-mono {{ $m['total_pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
              {{ $m['total_pnl'] >= 0 ? '+' : '' }}Rp{{ number_format($m['total_pnl'], 0, ',', '.') }}
            </td>
          </tr>
          @endforeach
        </tbody>
      </table>
    </div>
  </div>
  @endif

  {{-- ── STRATEGI LAIN (arsip, TIDAK dihitung ke kartu resmi di atas) ── --}}
  @if(!empty($strategyBreakdown))
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
      @if($scope === 'all')
        📁 Strategi Lain (rincian -- SUDAH ikut kehitung di kartu "Semua Strategi" di atas)
      @else
        📁 Strategi Lain (di luar GABUNGAN — arsip riset, bukan angka resmi)
      @endif
    </h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
      @foreach($strategyBreakdown as $sb)
      <div class="glass-card border border-slate-800/60 rounded-xl p-3 bg-slate-900/30">
        <p class="text-[11px] text-slate-400 font-medium mb-1">{{ $sb['label'] }}</p>
        <div class="flex items-baseline gap-2">
          <span class="text-lg font-bold text-slate-200">{{ $sb['closed'] }}</span>
          <span class="text-[10px] text-slate-500">closed</span>
          @if($sb['open'] > 0)
            <span class="text-[10px] text-sky-400">+{{ $sb['open'] }} open</span>
          @endif
        </div>
        @if($sb['win_rate'] !== null)
          <p class="text-[11px] mt-1 {{ $sb['total_pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
            WR {{ $sb['win_rate'] }}% • Rp{{ number_format($sb['total_pnl'], 0, ',', '.') }}
          </p>
        @endif
        @if($sb['episode_count'] !== null && $sb['episode_count'] > 0)
          <p class="text-[10px] text-slate-500 mt-1 pt-1 border-t border-slate-800/60"
             title="Trigger berdekatan (jeda <=15 hari, saham sama) dianggap 1 kejadian pasar.">
            ≈ {{ $sb['episode_count'] }} episode ({{ $sb['episode_win_rate'] }}% WR)
          </p>
        @endif
      </div>
      @endforeach
    </div>
  </div>
  @endif

  {{-- ── CLOSED TRADES ── --}}
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
      <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider">
        📋 Riwayat Trading ({{ $closedPage->total() }}{{ $closedPage->total() !== $closed->count() ? ' dari '.$closed->count() : '' }})
      </h2>
      {{-- Fase CM: filter strategi/saham + pagination -- 374+ baris terlalu berat dipindai
           tanpa ini. Form GET biasa (bukan JS) supaya bisa di-bookmark/refresh. --}}
      <form method="GET" class="flex items-center gap-2 text-xs">
        <input type="hidden" name="scope" value="{{ $scope }}">
        <select name="filter_strategy" onchange="this.form.submit()"
                class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300">
          <option value="">Semua Strategi</option>
          @foreach($historyStrategyOptions as $opt)
            <option value="{{ $opt }}" {{ $historyStrategy === $opt ? 'selected' : '' }}>{{ strtoupper($opt) }}</option>
          @endforeach
        </select>
        <select name="filter_ticker" onchange="this.form.submit()"
                class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300">
          <option value="">Semua Saham</option>
          @foreach($historyTickerOptions as $opt)
            <option value="{{ $opt }}" {{ $historyTicker === $opt ? 'selected' : '' }}>{{ $opt }}</option>
          @endforeach
        </select>
        @if($historyStrategy || $historyTicker)
          <a href="{{ route('trades.laporan', ['scope' => $scope]) }}"
             class="text-slate-500 hover:text-slate-300 underline">Reset</a>
        @endif
      </form>
    </div>

    @if($closedPage->total() === 0 && ($historyStrategy || $historyTicker))
    <div class="glass-card border border-slate-800/80 rounded-2xl p-8 text-center text-sm text-slate-500">
      Tidak ada trade yang cocok dengan filter ini.
    </div>
    @elseif($closed->count() > 0)
    <div class="glass-card border border-slate-800/80 rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-800 text-[11px] text-slate-500 uppercase">
              <th class="px-4 py-3 text-left">Saham</th>
              <th class="px-4 py-3 text-left">Tanggal</th>
              <th class="px-4 py-3 text-right">Entry</th>
              <th class="px-4 py-3 text-right">Exit</th>
              <th class="px-4 py-3 text-right">PnL/lbr</th>
              <th class="px-4 py-3 text-right">Lot</th>
              <th class="px-4 py-3 text-right">PnL Total</th>
              <th class="px-4 py-3 text-right">PnL %</th>
              <th class="px-4 py-3 text-right">Actual R:R</th>
              <th class="px-4 py-3 text-center">Hasil</th>
              <th class="px-4 py-3 text-center">DSS Akurat?</th>
              <th class="px-4 py-3 text-right">Hold</th>
              <th class="px-4 py-3 text-center">Aksi</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/50">
            @foreach($closedPage as $trade)
            <tr class="hover:bg-slate-800/30 transition">
              <td class="px-4 py-3">
                @php
                  $strategyConfig = match($trade->strategy_label) {
                    'gabungan'              => ['bg-sky-500/10 text-sky-400 border-sky-500/30', 'GABUNGAN'],
                    'momentum'              => ['bg-amber-500/10 text-amber-400 border-amber-500/30', 'MOMENTUM'],
                    'ai_tp30'               => ['bg-purple-500/10 text-purple-400 border-purple-500/30', 'AI TP30'],
                    'legacy_stock_only'     => ['bg-slate-700/40 text-slate-400 border-slate-600/60', 'LAMA: STOCK-ONLY'],
                    'legacy_ab_ac'          => ['bg-slate-700/40 text-slate-400 border-slate-600/60', 'LAMA: AB/AC'],
                    'manual_discretionary'  => ['bg-slate-700/40 text-slate-300 border-slate-600/60', 'MANUAL'],
                    'bottom_rebound'        => ['bg-emerald-500/10 text-emerald-400 border-emerald-500/30', 'BOTTOM-REBOUND'],
                    default                 => ['bg-slate-800 text-slate-500 border-slate-700', '—'],
                  };
                @endphp
                <div class="flex items-center gap-2">
                  <span class="font-bold text-slate-100">{{ $trade->stock->code }}</span>
                  <span class="text-[10px] text-slate-500">
                    {{ strtoupper($trade->signal_quality ?? '') }}
                  </span>
                </div>
                <span class="inline-block mt-1 px-1.5 py-0.5 rounded text-[9px] font-medium border {{ $strategyConfig[0] }}">
                  {{ $strategyConfig[1] }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-400">
                <div class="text-[11px]">
                  <div>{{ $trade->entry_date->format('d M y') }}</div>
                  <div class="text-slate-600">→ {{ $trade->exit_date?->format('d M y') }}</div>
                </div>
              </td>
              <td class="px-4 py-3 text-right font-mono text-slate-300">
                {{ number_format($trade->entry_price, 0, ',', '.') }}
              </td>
              <td class="px-4 py-3 text-right font-mono text-slate-300">
                {{ number_format($trade->exit_price, 0, ',', '.') }}
              </td>
              <td class="px-4 py-3 text-right font-mono text-sm
                {{ $trade->pnl_per_share >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                {{ $trade->pnl_per_share >= 0 ? '+' : '' }}{{ number_format($trade->pnl_per_share, 0, ',', '.') }}
              </td>
              <td class="px-4 py-3 text-right text-slate-400">
                {{ number_format($trade->lot_size / 100) }}
              </td>
              <td class="px-4 py-3 text-right font-mono font-bold
                {{ $trade->pnl_total >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                {{ $trade->pnl_total >= 0 ? '+' : '' }}Rp {{ number_format($trade->pnl_total, 0, ',', '.') }}
              </td>
              <td class="px-4 py-3 text-right font-mono
                {{ $trade->pnl_percent >= 0 ? 'text-green-400' : 'text-rose-400' }}">
                {{ $trade->pnl_percent >= 0 ? '+' : '' }}{{ $trade->pnl_percent }}%
              </td>
              <td class="px-4 py-3 text-right font-mono
                {{ ($trade->actual_rr ?? 0) >= 1.5 ? 'text-green-400' :
                   (($trade->actual_rr ?? 0) >= 0 ? 'text-amber-400' : 'text-rose-400') }}">
                1:{{ $trade->actual_rr ?? '-' }}
              </td>
              <td class="px-4 py-3 text-center">
                @php
                  $resultConfig = match($trade->result) {
                    'hit_target_1' => ['bg-green-500/10 text-green-400 border-green-500/30', '✅ TP1 Hit'],
                    'hit_target_2' => ['bg-emerald-500/10 text-emerald-400 border-emerald-500/30', '✅ TP2 Hit'],
                    'stop_loss'    => ['bg-rose-500/10 text-rose-400 border-rose-500/30', '❌ SL Hit'],
                    'manual_close' => ['bg-amber-500/10 text-amber-400 border-amber-500/30', '📌 Manual'],
                    default        => ['bg-slate-800 text-slate-400 border-slate-700', '—'],
                  };
                @endphp
                <span class="px-2 py-0.5 rounded-full text-[10px] border {{ $resultConfig[0] }}">
                  {{ $resultConfig[1] }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                @php
                  $dssCorrect = ($trade->dss_prediction === 'up' &&
                                 in_array($trade->result, ['hit_target_1','hit_target_2']))
                             || ($trade->dss_prediction === 'down' &&
                                 $trade->result === 'stop_loss');
                  $dssWrong   = ($trade->dss_prediction === 'up' && $trade->result === 'stop_loss')
                             || ($trade->dss_prediction === 'down' &&
                                 in_array($trade->result, ['hit_target_1','hit_target_2']));
                @endphp
                @if($dssCorrect)
                  <span class="text-green-400 text-sm" title="DSS prediksi benar">✅</span>
                @elseif($dssWrong)
                  <span class="text-rose-400 text-sm" title="DSS prediksi salah">❌</span>
                @else
                  <span class="text-slate-600">—</span>
                @endif
              </td>
              <td class="px-4 py-3 text-right text-slate-400 text-[11px]">
                {{ $trade->holding_days ?? '-' }}h
              </td>
              <td class="px-4 py-3 text-center">
                <div class="flex items-center justify-center gap-1.5">
                  <a href="{{ route('trade-journal.edit', $trade) }}"
                     class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-[11px]
                            hover:bg-sky-500/10 hover:border-sky-500/30 hover:text-sky-400 transition">
                    Edit
                  </a>
                  <form action="{{ route('trades.destroy', $trade) }}" method="POST"
                        onsubmit="return confirm('Hapus trade {{ $trade->stock->code }} ({{ $trade->entry_date->format('d M y') }}) ini?')">
                    @csrf @method('DELETE')
                    <button class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-[11px]
                                   hover:bg-rose-500/10 hover:border-rose-500/30 hover:text-rose-400 transition">
                      Hapus
                    </button>
                  </form>
                </div>
              </td>
            </tr>
            @endforeach
          </tbody>
        </table>
      </div>
      @if($closedPage->hasPages())
      <div class="flex items-center justify-between px-4 py-3 border-t border-slate-800/80">
        <p class="text-[11px] text-slate-500">
          Menampilkan {{ $closedPage->firstItem() }}–{{ $closedPage->lastItem() }} dari {{ $closedPage->total() }} trade
        </p>
        {{ $closedPage->appends(request()->query())->onEachSide(1)->links('components.pagination-dark') }}
      </div>
      @endif
    </div>
    @else
    <div class="glass-card border border-slate-800/80 rounded-2xl p-8 text-center">
      <div class="text-4xl mb-3">📋</div>
      <p class="text-slate-400 font-medium">Belum ada trade yang ditutup</p>
      <p class="text-sm text-slate-500 mt-1">
        Trade yang ditutup akan muncul di sini beserta analisis akurasi DSS
      </p>
    </div>
    @endif
  </div>

</div>
</x-app-layout>
