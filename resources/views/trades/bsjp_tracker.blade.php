<x-app-layout>
<div class="space-y-6" x-data="{
  buyModalOpen: false,
  sellModalOpen: false,
  sellTarget: null,
  calcLots(price, capital) {
    if (!price || price <= 0 || !capital || capital <= 0) return 0;
    return Math.floor(capital / (price * 100 * 1.0015));
  },
  openSellModal(trade) {
    this.sellTarget = trade;
    this.sellModalOpen = true;
  }
}">

  {{-- ── HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <div class="flex items-center gap-2">
        <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-amber-500/20 text-amber-300 border border-amber-500/40">
          LIVE TRADE TRACKER
        </span>
        <span class="text-xs text-slate-500 font-mono">BSJP MOMENTUM</span>
      </div>
      <h1 class="text-2xl font-extrabold text-slate-100 mt-1 flex items-center gap-2">
        <x-heroicon-o-bolt class="w-7 h-7 text-amber-400" />
        Pencatatan Portofolio BSJP (Beli Sore Jual Pagi)
      </h1>
      <p class="text-sm text-slate-400 mt-0.5">
        Pencatatan eksekusi trading riil modal terukur <strong>Rp 20.000.000</strong>. Beli di Pre-Closing (15:50 WIB) &times; Take Profit di Open (09:00 WIB).
      </p>
    </div>

    <div class="flex items-center gap-2">
      <button type="button" @click="buyModalOpen = true"
              class="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 transition">
        <x-heroicon-o-plus class="w-4 h-4" />
        Catat Beli Baru
      </button>
      <a href="{{ route('trades.radar') }}"
         class="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-300 border border-slate-700/80 transition">
        <x-heroicon-o-signal class="w-4 h-4 text-amber-400" />
        Radar Sinyal
      </a>
      <a href="{{ route('trades.radar-log') }}"
         class="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-300 border border-slate-700/80 transition">
        <x-heroicon-o-clipboard-document-list class="w-4 h-4 text-sky-400" />
        Radar Log
      </a>
    </div>
  </div>

  {{-- ── FLASH STATUS ── --}}
  @if(session('status'))
    <div class="glass-card border border-emerald-500/40 bg-emerald-500/[0.06] rounded-2xl px-4 py-3 text-sm text-emerald-300 flex items-center gap-2 shadow-sm">
      <x-heroicon-o-check-circle class="w-5 h-5 shrink-0 text-emerald-400" />
      <span>{{ session('status') }}</span>
    </div>
  @endif

  {{-- ── METRIC CARDS ── --}}
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3.5">
    {{-- Saldo Modal --}}
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80 bg-slate-900/50">
      <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wider mb-1">Saldo Modal Berjalan</p>
      <p class="text-xl font-bold font-mono text-slate-100">
        Rp {{ number_format($stats['current_capital'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] mt-1 font-medium font-mono"
         class="{{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
        {{ $stats['total_realized_pnl'] >= 0 ? '+' : '' }}{{ number_format($stats['total_capital_growth_pct'], 2) }}% dari Rp 20Jt
      </p>
    </div>

    {{-- Realized PnL Rp --}}
    <div class="glass-card rounded-2xl p-4 border {{ $stats['total_realized_pnl'] >= 0 ? 'border-emerald-500/30 bg-emerald-500/[0.03]' : 'border-rose-500/30 bg-rose-500/[0.03]' }}">
      <p class="text-[10px] uppercase font-semibold tracking-wider mb-1 {{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400/80' : 'text-rose-400/80' }}">
        Total Realized P&L
      </p>
      <p class="text-xl font-bold font-mono {{ $stats['total_realized_pnl'] >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
        {{ $stats['total_realized_pnl'] >= 0 ? '+' : '' }}Rp {{ number_format($stats['total_realized_pnl'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Net setelah fee broker 0.4%</p>
    </div>

    {{-- Win Rate --}}
    <div class="glass-card rounded-2xl p-4 border border-amber-500/20 bg-amber-500/[0.02]">
      <p class="text-[10px] text-amber-400/80 uppercase font-semibold tracking-wider mb-1">Win Rate Live</p>
      <p class="text-xl font-bold font-mono text-amber-300">
        {{ number_format($stats['win_rate'], 1) }}%
      </p>
      <p class="text-[11px] text-slate-400 mt-1 font-mono">
        <span class="text-emerald-400 font-bold">{{ $stats['win_trades'] }} Win</span> &times; <span class="text-rose-400 font-bold">{{ $stats['loss_trades'] }} Loss</span>
      </p>
    </div>

    {{-- Total Selesai --}}
    <div class="glass-card rounded-2xl p-4 border border-slate-800/80 bg-slate-900/50">
      <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wider mb-1">Trade Selesai</p>
      <p class="text-xl font-bold font-mono text-slate-200">
        {{ $stats['total_trades'] }} Trade
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Holding 1 malam (Overnight)</p>
    </div>

    {{-- Posisi Aktif --}}
    <div class="glass-card rounded-2xl p-4 border border-sky-500/30 bg-sky-500/[0.04] col-span-2 md:col-span-1">
      <p class="text-[10px] text-sky-400/80 uppercase font-semibold tracking-wider mb-1 flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse"></span>
        Posisi Aktif (Hold)
      </p>
      <p class="text-xl font-bold font-mono text-sky-300">
        {{ $stats['open_count'] }} Posisi
      </p>
      <p class="text-[11px] text-sky-400/70 mt-1">Menunggu Jual Open 09:00</p>
    </div>
  </div>

  {{-- ── SEKSI 1: POSISI AKTIF (HOLDING OVERNIGHT) ── --}}
  <div class="glass-card rounded-2xl border border-slate-800/80 p-5 space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-base font-bold text-slate-100 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-sky-400 animate-pulse"></span>
          Posisi Aktif yang Sedang Berjalan (Holding Overnight)
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">Saham yang telah dibeli sore kemarin dan siap dieksekusi jual pada pembukaan bursa 09:00 WIB.</p>
      </div>
      <span class="text-xs font-mono font-bold px-2.5 py-1 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/30">
        {{ $openPositions->count() }} Saham
      </span>
    </div>

    @if($openPositions->isEmpty())
      <div class="p-8 text-center border border-dashed border-slate-800 rounded-xl">
        <x-heroicon-o-inbox class="w-10 h-10 text-slate-600 mx-auto mb-2" />
        <p class="text-sm font-medium text-slate-400">Tidak ada posisi BSJP yang sedang aktif.</p>
        <p class="text-xs text-slate-500 mt-1">Pilih saham dari Radar Sinyal sore nanti jam 15:35 WIB dan klik "Beli Rp 20 Jt".</p>
      </div>
    @else
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-300">
          <thead class="text-[10px] uppercase font-semibold text-slate-500 border-b border-slate-800 bg-slate-900/60">
            <tr>
              <th class="py-3 px-3">Ticker / Emiten</th>
              <th class="py-3 px-3">Tgl Beli (Sore)</th>
              <th class="py-3 px-3">Harga Beli</th>
              <th class="py-3 px-3">Lot (Modal Rp 20 Jt)</th>
              <th class="py-3 px-3">Total Modal Riil</th>
              <th class="py-3 px-3">Target TP (+2.5%)</th>
              <th class="py-3 px-3">Stop Loss (-3%)</th>
              <th class="py-3 px-3 text-right">Aksi Eksekusi Jual</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60 font-mono">
            @foreach($openPositions as $pos)
              <tr class="hover:bg-slate-800/30 transition">
                <td class="py-3 px-3 font-sans">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-sm text-slate-100">{{ $pos->ticker }}</span>
                    <span class="text-[9px] px-1.5 py-0.5 rounded border {{ $pos->category === 'rocket' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }}">
                      {{ $pos->category === 'rocket' ? '🚀 Rocket' : '🎯 Sweetspot' }}
                    </span>
                  </div>
                  <p class="text-[11px] text-slate-400 truncate max-w-[180px]">{{ $pos->stock_name }}</p>
                </td>
                <td class="py-3 px-3 text-slate-400">{{ $pos->signal_date->format('d M Y') }}</td>
                <td class="py-3 px-3 font-bold text-slate-100">Rp {{ number_format($pos->entry_price, 0, ',', '.') }}</td>
                <td class="py-3 px-3 font-bold text-amber-300">{{ number_format($pos->lots) }} Lot</td>
                <td class="py-3 px-3 text-slate-200">Rp {{ number_format($pos->lots * 100 * $pos->entry_price, 0, ',', '.') }}</td>
                <td class="py-3 px-3 text-emerald-400 font-bold">Rp {{ number_format($pos->target_tp, 0, ',', '.') }}</td>
                <td class="py-3 px-3 text-rose-400 font-bold">Rp {{ number_format($pos->stop_loss, 0, ',', '.') }}</td>
                <td class="py-3 px-3 text-right font-sans">
                  <button type="button" @click="openSellModal({{ json_encode($pos) }})"
                          class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white shadow transition inline-flex items-center gap-1">
                    <x-heroicon-o-banknotes class="w-3.5 h-3.5" />
                    Catat Jual (Exit)
                  </button>
                </td>
              </tr>
            @endforeach
          </tbody>
        </table>
      </div>
    @endif
  </div>

  {{-- ── SEKSI 2: RIWAYAT TRANSAKSI SELESAI (CLOSED TRADES) ── --}}
  <div class="glass-card rounded-2xl border border-slate-800/80 p-5 space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-base font-bold text-slate-100 flex items-center gap-2">
          <x-heroicon-o-check-badge class="w-5 h-5 text-emerald-400" />
          Riwayat Transaksi BSJP Selesai
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">Catatan performa transaksi yang telah direalisasikan (Win Rate & Return bersih).</p>
      </div>
      <span class="text-xs font-mono font-bold px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
        {{ $closedTrades->count() }} Selesai
      </span>
    </div>

    @if($closedTrades->isEmpty())
      <div class="p-8 text-center border border-dashed border-slate-800 rounded-xl">
        <p class="text-sm font-medium text-slate-400">Belum ada riwayat transaksi selesai.</p>
        <p class="text-xs text-slate-500 mt-1">Setelah mencatat penjualan di pembukaan pagi, data historis akan terkumpul di sini.</p>
      </div>
    @else
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-300">
          <thead class="text-[10px] uppercase font-semibold text-slate-500 border-b border-slate-800 bg-slate-900/60">
            <tr>
              <th class="py-3 px-3">Tgl Beli &rarr; Jual</th>
              <th class="py-3 px-3">Ticker</th>
              <th class="py-3 px-3">Beli Sore</th>
              <th class="py-3 px-3">Jual Pagi</th>
              <th class="py-3 px-3">Lot</th>
              <th class="py-3 px-3">Tipe Exit</th>
              <th class="py-3 px-3">Gross P&L</th>
              <th class="py-3 px-3">Net P&L (%)</th>
              <th class="py-3 px-3 text-right">Net Cuan (Rp)</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60 font-mono">
            @foreach($closedTrades as $trade)
              @php
                $isWin = $trade->net_pnl_rp > 0;
                $isLoss = $trade->net_pnl_rp < 0;
              @endphp
              <tr class="hover:bg-slate-800/30 transition">
                <td class="py-3 px-3 text-slate-400">
                  {{ $trade->signal_date->format('d/m') }} &rarr; {{ $trade->exited_at ? $trade->exited_at->format('d/m') : '-' }}
                </td>
                <td class="py-3 px-3 font-sans font-bold text-slate-100">
                  {{ $trade->ticker }}
                </td>
                <td class="py-3 px-3 text-slate-300">Rp {{ number_format($trade->entry_price, 0, ',', '.') }}</td>
                <td class="py-3 px-3 font-bold text-slate-100">Rp {{ number_format($trade->exit_price, 0, ',', '.') }}</td>
                <td class="py-3 px-3 text-slate-400">{{ number_format($trade->lots) }} Lot</td>
                <td class="py-3 px-3 font-sans">
                  <span class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    {{ str_replace('_', ' ', $trade->exit_type ?? 'OPEN_MARKET') }}
                  </span>
                </td>
                <td class="py-3 px-3 {{ $trade->gross_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400' }}">
                  {{ sprintf('%+.2f%%', $trade->gross_pnl_pct) }}
                </td>
                <td class="py-3 px-3 font-bold {{ $isWin ? 'text-emerald-400' : ($isLoss ? 'text-rose-400' : 'text-slate-400') }}">
                  {{ sprintf('%+.2f%%', $trade->net_pnl_pct) }}
                </td>
                <td class="py-3 px-3 text-right font-bold {{ $isWin ? 'text-emerald-400' : ($isLoss ? 'text-rose-400' : 'text-slate-400') }}">
                  {{ $isWin ? '+' : '' }}Rp {{ number_format($trade->net_pnl_rp, 0, ',', '.') }}
                </td>
              </tr>
            @endforeach
          </tbody>
        </table>
      </div>
    @endif
  </div>

  {{-- ── MODAL CATAT BELI ── --}}
  <div x-show="buyModalOpen" x-cloak class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
    <div @click.away="buyModalOpen = false" class="glass-card rounded-2xl border border-slate-700 bg-slate-900 p-6 w-full max-w-md space-y-4 shadow-2xl">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-base font-bold text-slate-100 flex items-center gap-2">
          <x-heroicon-o-shopping-cart class="w-5 h-5 text-emerald-400" />
          Catat Beli Saham BSJP (Sore 15:50)
        </h3>
        <button type="button" @click="buyModalOpen = false" class="text-slate-400 hover:text-slate-200">
          <x-heroicon-o-x-mark class="w-5 h-5" />
        </button>
      </div>

      <form action="{{ route('trades.bsjp-tracker.buy') }}" method="POST" class="space-y-3.5" x-data="{
        buyPrice: '',
        capital: 20000000,
        calcLotsInput() {
          return calcLots(parseFloat(this.buyPrice) || 0, parseFloat(this.capital) || 0);
        }
      }">
        @csrf
        <div>
          <label class="block text-xs font-semibold text-slate-300 mb-1">Kode Ticker Saham</label>
          <input type="text" name="ticker" required placeholder="Contoh: PSDN, BKDP, CENT" uppercase
                 class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-bold uppercase focus:ring-1 focus:ring-emerald-500" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Harga Beli Sore (Rp)</label>
            <input type="number" name="entry_price" required min="1" step="1" x-model="buyPrice" placeholder="Contoh: 144"
                   class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-mono font-bold focus:ring-1 focus:ring-emerald-500" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Alokasi Modal (Rp)</label>
            <input type="number" name="capital" min="100000" step="100000" x-model="capital"
                   class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-mono focus:ring-1 focus:ring-emerald-500" />
          </div>
        </div>

        {{-- Estimasi Lot --}}
        <div class="p-3 rounded-xl bg-slate-800/50 border border-slate-800 flex items-center justify-between text-xs">
          <span class="text-slate-400">Estimasi Jumlah Lot:</span>
          <span class="font-mono font-bold text-amber-300 text-sm" x-text="calcLotsInput() + ' Lot'"></span>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Kategori</label>
            <select name="category" class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-xs text-slate-100">
              <option value="sweetspot">🎯 Sweetspot (4% - 15%)</option>
              <option value="rocket">🚀 Super Rocket (≥15%)</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Tanggal Beli</label>
            <input type="date" name="signal_date" value="{{ now('Asia/Jakarta')->toDateString() }}"
                   class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-xs text-slate-100" />
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-2">
          <button type="button" @click="buyModalOpen = false" class="px-3.5 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition">
            Batal
          </button>
          <button type="submit" class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow-lg transition">
            Simpan Eksekusi Beli
          </button>
        </div>
      </form>
    </div>
  </div>

  {{-- ── MODAL CATAT JUAL (EXIT) ── --}}
  <div x-show="sellModalOpen" x-cloak class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
    <div @click.away="sellModalOpen = false" class="glass-card rounded-2xl border border-slate-700 bg-slate-900 p-6 w-full max-w-md space-y-4 shadow-2xl">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-base font-bold text-slate-100 flex items-center gap-2">
          <x-heroicon-o-banknotes class="w-5 h-5 text-emerald-400" />
          Catat Penjualan (Jual di Open 09:00)
        </h3>
        <button type="button" @click="sellModalOpen = false" class="text-slate-400 hover:text-slate-200">
          <x-heroicon-o-x-mark class="w-5 h-5" />
        </button>
      </div>

      <template x-if="sellTarget">
        <form :action="'{{ url('/trades/bsjp-tracker') }}/' + sellTarget.id + '/sell'" method="POST" class="space-y-3.5" x-data="{
          sellPrice: '',
          calcProfit() {
            if (!this.sellPrice || this.sellPrice <= 0 || !sellTarget) return 0;
            const entry = sellTarget.entry_price;
            const lots = sellTarget.lots;
            const buyCost = lots * 100 * entry * 1.0015;
            const netProceeds = lots * 100 * parseFloat(this.sellPrice) * (1 - 0.0025);
            return netProceeds - buyCost;
          },
          calcPct() {
            if (!this.sellPrice || this.sellPrice <= 0 || !sellTarget) return 0;
            return ((parseFloat(this.sellPrice) - sellTarget.entry_price) / sellTarget.entry_price) * 100;
          }
        }">
          @csrf
          <div class="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/80 space-y-1 text-xs">
            <div class="flex justify-between text-slate-300">
              <span>Saham:</span>
              <span class="font-bold text-slate-100" x-text="sellTarget.ticker"></span>
            </div>
            <div class="flex justify-between text-slate-300">
              <span>Harga Beli Sore:</span>
              <span class="font-mono font-bold" x-text="'Rp ' + Number(sellTarget.entry_price).toLocaleString('id-ID')"></span>
            </div>
            <div class="flex justify-between text-slate-300">
              <span>Jumlah Lot:</span>
              <span class="font-mono font-bold text-amber-300" x-text="Number(sellTarget.lots).toLocaleString('id-ID') + ' Lot'"></span>
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Harga Jual / Open Pembukaan (Rp)</label>
            <input type="number" name="exit_price" required min="1" step="1" x-model="sellPrice" placeholder="Contoh: 147"
                   class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-mono font-bold focus:ring-1 focus:ring-emerald-500" />
          </div>

          {{-- Estimasi Realisasi P&L --}}
          <div class="p-3 rounded-xl bg-slate-800/50 border border-slate-800 flex items-center justify-between text-xs">
            <span class="text-slate-400">Estimasi Bersih (Net PnL):</span>
            <span class="font-mono font-bold text-sm"
                  :class="calcProfit() >= 0 ? 'text-emerald-400' : 'text-rose-400'"
                  x-text="(calcProfit() >= 0 ? '+' : '') + 'Rp ' + Math.round(calcProfit()).toLocaleString('id-ID') + ' (' + calcPct().toFixed(2) + '%)'"></span>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-300 mb-1">Tipe Eksekusi</label>
            <select name="exit_type" class="w-full rounded-xl bg-slate-800/80 border border-slate-700 px-3 py-2 text-xs text-slate-100">
              <option value="OPEN_MARKET">Jual Pembukaan Open (09:00 WIB)</option>
              <option value="TARGET_TP">Kena Target TP (+2.5%)</option>
              <option value="STOP_LOSS">Kena Stop Loss (-3%)</option>
              <option value="MANUAL">Manual / Intraday</option>
            </select>
          </div>

          <div class="flex items-center justify-end gap-2 pt-2">
            <button type="button" @click="sellModalOpen = false" class="px-3.5 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition">
              Batal
            </button>
            <button type="submit" class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow-lg transition">
              Konfirmasi Jual Selesai
            </button>
          </div>
        </form>
      </template>
    </div>
  </div>

</div>
</x-app-layout>
