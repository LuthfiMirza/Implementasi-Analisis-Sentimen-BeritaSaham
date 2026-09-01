<x-app-layout>
<div class="space-y-6">

  {{-- ── HEADER ── --}}
  <div class="flex items-center justify-between">
    <div>
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5">Trade Journal</h1>
      <p class="text-sm text-slate-400 mt-1">Rekam jejak sinyal DSS vs hasil aktual pasar</p>
    </div>
    <button onclick="document.getElementById('addTradeModal').classList.remove('hidden')"
            class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl
                   bg-sky-500 hover:bg-sky-400 text-slate-900 font-semibold text-sm transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
      </svg>
      Catat Trade Baru
    </button>
  </div>

  {{-- ── PREVIEW RINGKAS + LINK KE LAPORAN LENGKAP ── --}}
  {{-- Fase CN/CO: halaman ini dulu berisi SEMUA (stats, episode per bulan, strategi lain,
       riwayat 374 baris) jadi terlalu panjang untuk kebutuhan harian (buka/tutup posisi, catat
       manual). Dipisah: /trades fokus operasional, /trades/laporan untuk analisis lengkap.
       Preview di sini SELALU GABUNGAN resmi (tidak ada toggle scope -- itu ada di laporan).
       Fase CO: 3 kartu terpisah (bukan bar datar) + "Trade Closed" (292, angka paling tidak
       bercerita) diganti Episode Independen -- lebih jujur menggambarkan performa. --}}
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
    <div class="glass-card rounded-2xl p-4 border
      {{ $preview['total_pnl'] >= 0 ? 'border-green-500/20 bg-green-500/[0.03]' : 'border-rose-500/20 bg-rose-500/[0.03]' }}">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1.5 flex items-center gap-1">
        <x-heroicon-o-banknotes class="w-3 h-3" /> Total PnL (GABUNGAN)
      </p>
      <p class="text-xl sm:text-2xl font-bold whitespace-nowrap
        {{ $preview['total_pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
        {{ $preview['total_pnl'] >= 0 ? '+' : '' }}Rp{{ number_format($preview['total_pnl'], 0, ',', '.') }}
      </p>
      <p class="text-[11px] text-slate-500 mt-1">Realized • {{ $preview['closed'] }} trade</p>
    </div>

    <div class="glass-card rounded-2xl p-4 border
      {{ $preview['win_rate'] >= 60 ? 'border-green-500/20 bg-green-500/[0.03]' :
         ($preview['win_rate'] >= 40 ? 'border-amber-500/20 bg-amber-500/[0.03]' : 'border-rose-500/20 bg-rose-500/[0.03]') }}">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1.5 flex items-center gap-1">
        <x-heroicon-o-check-badge class="w-3 h-3" /> Win Rate
      </p>
      <p class="text-xl sm:text-2xl font-bold
        {{ $preview['win_rate'] >= 60 ? 'text-green-400' :
           ($preview['win_rate'] >= 40 ? 'text-amber-400' : 'text-rose-400') }}">
        {{ $preview['win_rate'] }}%
      </p>
      <p class="text-[11px] mt-1">
        <span class="text-green-400">{{ $preview['win'] }}W</span>
        <span class="text-slate-600">·</span>
        <span class="text-rose-400">{{ $preview['loss'] }}L</span>
      </p>
    </div>

    <div class="glass-card rounded-2xl p-4 border
      {{ $preview['episode_win_rate'] >= 60 ? 'border-sky-500/20 bg-sky-500/[0.03]' : 'border-slate-800/80' }}">
      <p class="text-[10px] text-slate-500 uppercase font-medium mb-1.5 flex items-center gap-1">
        <x-heroicon-o-chart-bar class="w-3 h-3" /> Episode Independen
      </p>
      <p class="text-xl sm:text-2xl font-bold text-sky-400">{{ $preview['episode_count'] }}</p>
      <p class="text-[11px] text-slate-500 mt-1">
        {{ $preview['episode_win_rate'] }}% WR • dari {{ $preview['closed'] }} trade mentah
      </p>
    </div>
  </div>

  <a href="{{ route('trades.laporan') }}"
     class="flex items-center justify-center gap-1.5 py-3 rounded-xl border border-sky-500/30
            bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 text-sm font-semibold transition">
    <x-heroicon-o-document-chart-bar class="w-4 h-4" /> Lihat Laporan Lengkap →
  </a>

  {{-- ── POSITION SIZING (Fase DD) ── --}}
  {{-- Modal trading + risk% per trade, dipakai kalkulator "lot disarankan" di modal Catat Trade
       Baru. Disimpan di system_settings (global, app ini single-trader) -- diletakkan di halaman
       operasional (bukan Admin) supaya gampang diubah kapan saja modal berubah. --}}
  @if(session('status'))
    <div class="rounded-xl border border-green-500/30 bg-green-500/10 text-green-300 text-sm px-4 py-2.5">
      ✓ {{ session('status') }}
    </div>
  @endif
  <div class="glass-card rounded-2xl p-4 border border-slate-800/80" x-data="{ editing: {{ $sizing['capital'] === null ? 'true' : 'false' }} }">
    <div class="flex items-center justify-between mb-2">
      <p class="text-[10px] text-slate-500 uppercase font-medium flex items-center gap-1">
        <x-heroicon-o-scale class="w-3 h-3" /> Position Sizing
      </p>
      <button type="button" @click="editing = !editing" class="text-[11px] text-sky-400 hover:text-sky-300" x-text="editing ? 'Batal' : 'Ubah'"></button>
    </div>

    <div x-show="!editing" x-cloak class="flex items-center gap-4 text-sm">
      @if($sizing['capital'] !== null)
        <span class="text-slate-300">Modal: <span class="font-mono font-semibold text-slate-100">Rp{{ number_format($sizing['capital'], 0, ',', '.') }}</span></span>
        <span class="text-slate-600">•</span>
        <span class="text-slate-300">Risk/trade: <span class="font-mono font-semibold text-slate-100">{{ $sizing['risk_pct'] }}%</span></span>
        <span class="text-slate-500 text-[11px]">(= Rp{{ number_format($sizing['capital'] * $sizing['risk_pct'] / 100, 0, ',', '.') }} maks rugi/trade)</span>
      @else
        <span class="text-amber-400 text-[13px]">Belum diatur -- kalkulator "lot disarankan" belum bisa dipakai. Klik "Ubah" utk isi modal Anda.</span>
      @endif
    </div>

    <form x-show="editing" x-cloak method="POST" action="{{ route('trades.position-sizing') }}" class="flex flex-wrap items-end gap-3 mt-1">
      @csrf
      <div>
        <label class="block text-[11px] text-slate-500 mb-1">Modal Trading (Rp)</label>
        <input type="number" name="capital" step="1" min="0" required
               value="{{ old('capital', $sizing['capital']) }}" placeholder="mis. 30000000"
               class="w-40 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-sky-500 focus:outline-none">
      </div>
      <div>
        <label class="block text-[11px] text-slate-500 mb-1">Risk per Trade (%)</label>
        <input type="number" name="risk_pct" step="0.1" min="0.1" max="100" required
               value="{{ old('risk_pct', $sizing['risk_pct']) }}"
               class="w-24 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-sky-500 focus:outline-none">
      </div>
      <p class="text-[10px] text-slate-500 mb-2">Standar risk management: 1-2% per trade.</p>
      <button type="submit" class="px-4 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-900 text-sm font-semibold transition">Simpan</button>
    </form>
  </div>

  {{-- ── TOTAL EXPOSURE WARNING (Fase DE) ── --}}
  {{-- Deteksi konsentrasi modal di posisi terbuka -- total exposure vs capital, plus breakdown
       per-sektor & per-ticker. Validasi nyata yg memicu fitur ini: pernah ada 3 dari 4 posisi
       terbuka semuanya DSSA (sektor Energy) = 75% total exposure -- kalau sektor itu kena
       sentimen negatif, ketiganya nyungsep bareng tanpa user sadar konsentrasinya sebesar itu. --}}
  @if($open->count() > 0)
  <div class="glass-card rounded-2xl p-4 border
    {{ $exposure['total_status'] === 'danger' ? 'border-rose-500/40 bg-rose-500/[0.04]' :
       ($exposure['total_status'] === 'warning' ? 'border-amber-500/30 bg-amber-500/[0.03]' : 'border-slate-800/80') }}">
    <div class="flex items-center justify-between mb-2">
      <p class="text-[10px] text-slate-500 uppercase font-medium flex items-center gap-1">
        <x-heroicon-o-chart-pie class="w-3 h-3" /> Total Exposure
      </p>
      @if($exposure['total_status'] === 'danger')
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold inline-flex items-center gap-1">
          <x-heroicon-o-exclamation-triangle class="w-3 h-3" /> OVER-EXPOSED
        </span>
      @elseif($exposure['total_status'] === 'warning')
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold inline-flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> WASPADA
        </span>
      @endif
    </div>

    <div class="flex items-baseline gap-3 mb-3">
      <p class="text-xl font-bold font-mono
        {{ $exposure['total_status'] === 'danger' ? 'text-rose-400' :
           ($exposure['total_status'] === 'warning' ? 'text-amber-400' : 'text-slate-100') }}">
        Rp{{ number_format($exposure['total_value'], 0, ',', '.') }}
      </p>
      @if($exposure['total_pct'] !== null)
        <p class="text-sm text-slate-500">= {{ $exposure['total_pct'] }}% dari modal Rp{{ number_format($sizing['capital'], 0, ',', '.') }}</p>
      @else
        <p class="text-[11px] text-amber-400">(isi Modal Trading di atas utk lihat % dari capital)</p>
      @endif
    </div>

    @if(!empty($exposure['by_sector']))
    <div class="space-y-2">
      <p class="text-[10px] text-slate-500 uppercase font-medium">Konsentrasi per Sektor</p>
      @foreach($exposure['by_sector'] as $s)
        <div>
          <div class="flex justify-between text-[11px] mb-0.5">
            <span class="text-slate-300">{{ $s['label'] }} <span class="text-slate-500">({{ implode(', ', $s['tickers']) }})</span></span>
            <span class="font-mono {{ $s['status'] === 'danger' ? 'text-rose-400' : ($s['status'] === 'warning' ? 'text-amber-400' : 'text-slate-400') }}">{{ $s['pct_of_exposure'] }}%</span>
          </div>
          <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full transition-all
              {{ $s['status'] === 'danger' ? 'bg-rose-500' : ($s['status'] === 'warning' ? 'bg-amber-500' : 'bg-sky-500') }}"
              style="width: {{ min(100, $s['pct_of_exposure']) }}%"></div>
          </div>
        </div>
      @endforeach
    </div>
    @endif
  </div>
  @endif

  {{-- ── OPEN POSITIONS ── --}}
  @if($open->count() > 0)
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-1.5">
      <span class="w-2 h-2 rounded-full bg-emerald-400"></span> Posisi Terbuka ({{ $open->count() }})
    </h2>
    <div class="space-y-3">
      @foreach($open as $trade)
      {{-- Bentuk blok, BUKAN shorthand @php(...) -- shorthand di sini akan tertelan oleh
           pre-pass storePhpBlocks() Blade yang mencari "@php(.*?)@endphp" di SELURUH file:
           tanpa @endphp sendiri, ia mencomot sampai ke @endphp blok $resultConfig di bawah
           dan meratakan semua @if/@else di antaranya jadi teks mentah (500 Undefined
           variable). Diverifikasi reproduksinya minimal sebelum diperbaiki -- lihat plan.md. --}}
      @php
        $lv = $live[$trade->id] ?? null;
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
      {{-- x-data di kartu ini bikin harga & P&L update sendiri (polling /api/stocks/{code}/quote,
           komponen tradePosition di resources/js/app.js) TANPA perlu refresh halaman -- nilai PHP
           di bawah cuma dipakai sebagai state AWAL sebelum polling pertama selesai. --}}
      <div class="glass-card border border-sky-500/20 bg-sky-500/5 rounded-2xl p-4"
           x-data="tradePosition(
             {{ (float) $trade->entry_price }},
             {{ (int) $trade->lot_size }},
             {{ $lv['last'] ?? 'null' }},
             {{ ($lv['is_live'] ?? false) ? 'true' : 'false' }},
             {{ ($lv['fetched_at'] ?? null) ? "'".$lv['fetched_at']."'" : 'null' }}
           )"
           x-init="startPolling('/api/stocks/{{ $trade->stock->code }}/quote')">
        <div class="flex items-start justify-between gap-4">

          {{-- Stock + Signal info --}}
          <div class="flex items-center gap-3">
            {{-- Fase CQ: logo asli emiten dari CDN publik TradingView (lihat
                 SyncStockLogosCommand) -- fallback ke inisial kode kalau logo_url kosong ATAU
                 gambarnya gagal dimuat (onerror), jangan sampai kartu kosong. --}}
            <div class="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/20
                        flex items-center justify-center font-bold text-sky-400 text-sm shrink-0 overflow-hidden">
              @if($trade->stock->logo_url)
                <img src="{{ $trade->stock->logo_url }}" alt="{{ $trade->stock->code }}"
                     class="w-full h-full object-contain p-1.5"
                     onerror="this.style.display='none'; this.nextElementSibling.classList.remove('hidden');">
                <span class="hidden">{{ $trade->stock->code }}</span>
              @else
                {{ $trade->stock->code }}
              @endif
            </div>
            <div>
              <div class="flex items-center gap-2">
                <p class="font-semibold text-slate-100">{{ $trade->stock->code }}</p>
                <span class="px-1.5 py-0.5 rounded text-[9px] font-medium border {{ $strategyConfig[0] }}">
                  {{ $strategyConfig[1] }}
                </span>
              </div>
              <p class="text-[11px] text-slate-400">
                {{-- Fase DM bug fix: dulu label ini pakai created_at (asumsi lama: SELALU sama
                     dengan tanggal+jam entry, karena job harian "pasti" jalan tepat 15:18 WIB
                     di entry_date yang sama -- asumsi ini TERBUKTI SALAH begitu job sempat
                     kelewat, mis. Mac tidur pas jam segitu). Sekarang pakai entry_date -- tanggal
                     TRADING sinyal ini berlaku, bukan kapan baris DB-nya dibuat. entry_date cuma
                     tanggal (selalu 00:00:00) jadi tidak ada jam palsu yang ditampilkan -- beda
                     dari jam "harga HH:MM WIB" di footer kartu, itu jam quote LIVE saat ini. --}}
                {{ $trade->stock->company_name }} • Masuk {{ $trade->entry_date->format('d M Y') }}
                @if($trade->created_at->timezone('Asia/Jakarta')->format('Y-m-d') !== $trade->entry_date->format('Y-m-d'))
                  {{-- Transparan kalau sinyal ini "telat" tersinkron (job harian sempat kelewat)
                       -- daripada diam-diam menyembunyikan gap-nya, dijelaskan eksplisit supaya
                       harga entry yang ditampilkan (closing entry_date, BUKAN harga hari ini)
                       tidak disalahartikan sebagai harga live saat baris ini muncul. --}}
                  <span class="text-slate-600" title="Job deteksi sinyal harian sempat tidak jalan tepat waktu -- sinyal ini baru tersinkron ke Trade Journal belakangan, harga entry di atas tetap harga closing {{ $trade->entry_date->format('d M Y') }}, bukan harga saat tersinkron.">
                    (tersinkron {{ $trade->created_at->timezone('Asia/Jakarta')->format('d M') }})
                  </span>
                @endif
              </p>
            </div>
          </div>

          {{-- P&L berjalan (reaktif) + badge kualitas sinyal --}}
          <div class="flex items-center gap-3">
            <div class="text-right" x-show="hasPrice">
              <p class="font-mono font-bold text-base leading-tight"
                 :class="pnl >= 0 ? 'text-green-400' : 'text-rose-400'">
                <span x-text="pnl >= 0 ? '+' : '−'"></span>Rp<span
                  x-text="Math.abs(pnl).toLocaleString('id-ID')"></span>
              </p>
              <p class="text-[11px] font-medium" :class="pnl >= 0 ? 'text-green-400/80' : 'text-rose-400/80'">
                <span x-text="pnl >= 0 ? '▲' : '▼'"></span>
                <span x-text="Math.abs(pnlPercent).toLocaleString('id-ID', {minimumFractionDigits:2, maximumFractionDigits:2})"></span>%
                <span class="text-slate-500">berjalan</span>
              </p>
            </div>
            <div class="text-right" x-show="!hasPrice" x-cloak>
              <p class="text-[11px] text-amber-400/90">Harga live tidak tersedia</p>
              <p class="text-[10px] text-slate-500">P&amp;L belum bisa dihitung</p>
            </div>
            <span class="px-2 py-1 rounded-full text-[10px] font-medium border
              {{ $trade->signal_quality === 'strong'
                 ? 'bg-green-500/10 text-green-400 border-green-500/30'
                 : 'bg-sky-500/10 text-sky-400 border-sky-500/30' }}">
              {{ strtoupper($trade->signal_quality ?? 'N/A') }}
            </span>
          </div>
        </div>

        {{-- Price levels --}}
        <div class="grid grid-cols-2 md:grid-cols-6 gap-3 mt-4">
          <div class="bg-slate-900/60 rounded-xl p-3">
            <p class="text-[10px] text-slate-500 mb-1">Entry</p>
            <p class="font-mono font-bold text-sky-400">
              {{ number_format($trade->entry_price, 0, ',', '.') }}
            </p>
          </div>
          <div class="rounded-xl p-3 border"
               :class="hasPrice ? (pnl >= 0 ? 'bg-green-500/5 border-green-500/20' : 'bg-rose-500/5 border-rose-500/20')
                                  : 'bg-slate-900/60 border-slate-700/40'">
            <p class="text-[10px] mb-1" :class="hasPrice ? (pnl >= 0 ? 'text-green-400' : 'text-rose-400') : 'text-slate-500'">
              Harga Kini
            </p>
            <p class="font-mono font-bold" :class="hasPrice ? (pnl >= 0 ? 'text-green-400' : 'text-rose-400') : 'text-slate-500'"
               x-text="hasPrice ? Math.round(last).toLocaleString('id-ID') : '—'"></p>
            <p class="text-[10px] text-slate-600" x-text="hasPrice ? (isLive ? 'live' : 'snapshot') : 'tidak tersedia'"></p>
          </div>
          <div class="bg-rose-500/5 rounded-xl p-3 border border-rose-500/20">
            <p class="text-[10px] text-rose-400 mb-1">Stop Loss</p>
            <p class="font-mono font-bold text-rose-400">
              {{ number_format($trade->stop_loss, 0, ',', '.') }}
            </p>
          </div>
          <div class="bg-green-500/5 rounded-xl p-3 border border-green-500/20">
            <p class="text-[10px] text-green-400 mb-1">Target 1 (2R)</p>
            <p class="font-mono font-bold text-green-400">
              {{ number_format($trade->target_1, 0, ',', '.') }}
            </p>
          </div>
          @if($trade->target_2)
          <div class="bg-emerald-500/5 rounded-xl p-3 border border-emerald-500/20">
            <p class="text-[10px] text-emerald-400 mb-1">Target 2 (3R)</p>
            <p class="font-mono font-bold text-emerald-400">
              {{ number_format($trade->target_2, 0, ',', '.') }}
            </p>
          </div>
          @endif
          <div class="bg-slate-900/60 rounded-xl p-3">
            <p class="text-[10px] text-slate-500 mb-1">Lot</p>
            <p class="font-mono font-bold text-slate-200">
              {{ number_format($trade->lot_size / 100) }} Lot
            </p>
            <p class="text-[10px] text-slate-600">{{ number_format($trade->lot_size) }} lbr</p>
          </div>
        </div>

        {{-- DSS info + Actions --}}
        <div class="flex items-center justify-between mt-3 pt-3 border-t border-slate-800">
          <div class="flex items-center gap-3 text-[11px] text-slate-400">
            {{-- dss_score/rr_ratio null pada trade dari sinyal otomatis (Fase BM) -- dulu
                 tampil "DSS: /100" dan "R:R Plan: 1:" yang terbaca seperti UI rusak. --}}
            <span>DSS:
              <span class="text-slate-200 font-medium">
                {{ $trade->dss_score !== null ? $trade->dss_score.'/100' : '—' }}
              </span>
            </span>
            <span>Prediksi:
              <span class="{{ $trade->dss_prediction === 'up' ? 'text-green-400' : 'text-slate-400' }} font-medium">
                {{ $trade->dss_prediction === 'up' ? '▲ UP' : ($trade->dss_prediction === 'down' ? '▼ DOWN' : '→ FLAT') }}
              </span>
            </span>
            <span>R:R Plan: {{ $trade->rr_ratio !== null ? '1:'.$trade->rr_ratio : '—' }}</span>
            <span class="text-slate-600" x-show="fetchedAt" x-cloak>• harga <span x-text="formatTime(fetchedAt)"></span></span>
          </div>
          <div class="flex gap-2">
            <button onclick="openCloseModal({{ $trade->id }}, '{{ $trade->stock->code }}', {{ $trade->entry_price }})"
                    class="px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/30
                           text-green-400 text-xs hover:bg-green-500/20 transition font-medium">
              ✓ Tutup Trade
            </button>
            <form action="{{ route('trades.destroy', $trade) }}" method="POST"
                  onsubmit="return confirm('Hapus trade ini?')">
              @csrf @method('DELETE')
              <button class="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700
                             text-slate-400 text-xs hover:bg-rose-500/10 hover:border-rose-500/30
                             hover:text-rose-400 transition">
                Hapus
              </button>
            </form>
          </div>
        </div>
      </div>
      @endforeach
    </div>
  </div>
  @endif

  {{-- ── EMPTY STATE (no trades at all) ── --}}
  @if($trades->isEmpty())
  <div class="glass-card border border-slate-800/80 rounded-2xl p-12 text-center">
    <x-heroicon-o-chart-bar-square class="w-12 h-12 text-slate-700 mx-auto mb-4" />
    <h3 class="text-lg font-semibold text-slate-200 mb-2">Belum Ada Trade Tercatat</h3>
    <p class="text-slate-400 text-sm max-w-md mx-auto mb-6">
      Mulai catat trade dari halaman Analytics saat sistem mendeteksi sinyal valid,
      atau klik tombol di bawah untuk input manual.
    </p>
    <button onclick="document.getElementById('addTradeModal').classList.remove('hidden')"
            class="px-6 py-2.5 rounded-xl bg-sky-500 hover:bg-sky-400
                   text-slate-900 font-semibold text-sm transition">
      + Catat Trade Pertama
    </button>
  </div>
  @endif

</div>

{{-- ══════════════════════════════════════════
     ADD TRADE MODAL
══════════════════════════════════════════ --}}
<div id="addTradeModal"
     class="{{ request()->hasAny(['stock_id','entry_price']) ? '' : 'hidden' }}
            fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
  <div class="w-full max-w-2xl bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl
              max-h-[90vh] overflow-y-auto">

    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-800">
      <div>
        <h2 class="font-bold text-slate-100 flex items-center gap-1.5">
          <x-heroicon-o-pencil-square class="w-4 h-4" /> Catat Trade Baru
        </h2>
        <p class="text-xs text-slate-500 mt-0.5">Data pre-filled dari sinyal DSS</p>
      </div>
      <button onclick="document.getElementById('addTradeModal').classList.add('hidden')"
              class="text-slate-500 hover:text-slate-300 transition text-xl leading-none">✕</button>
    </div>

    <form action="{{ route('trades.store') }}" method="POST" class="p-6 space-y-4">
      @csrf

      {{-- Saham + Tanggal --}}
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs text-slate-400 font-medium mb-1.5">Saham</label>
          <select name="stock_id" id="tradeStockSelect" required onchange="updateExposureWarning()"
                  class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                         text-sm text-slate-200 focus:border-sky-500 focus:outline-none">
            @foreach($stocks as $s)
              <option value="{{ $s->id }}" data-sector="{{ $s->sector ?? 'Lainnya' }}" data-code="{{ $s->code }}"
                {{ request('stock_id') == $s->id ? 'selected' : '' }}>
                {{ $s->code }} — {{ $s->company_name }}
              </option>
            @endforeach
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-400 font-medium mb-1.5">Entry Date</label>
          <input type="date" name="entry_date" required
                 value="{{ request('entry_date', now()->format('Y-m-d')) }}"
                 class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                        text-sm text-slate-200 focus:border-sky-500 focus:outline-none">
        </div>
      </div>

      {{-- Entry + Stop --}}
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs text-slate-400 font-medium mb-1.5">
            Entry Price
            <span class="text-sky-400 ml-1">
              (zone: {{ request('entry_zone_low') }}–{{ request('entry_zone_high') }})
            </span>
          </label>
          <input type="number" name="entry_price" required step="1" id="tradeEntryPriceInput"
                 value="{{ request('entry_price') }}" oninput="updateSuggestedLot(); updateExposureWarning();"
                 class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                        text-sm text-slate-200 focus:border-sky-500 focus:outline-none font-mono">
        </div>
        <div>
          <label class="block text-xs text-rose-400 font-medium mb-1.5">Stop Loss</label>
          <input type="number" name="stop_loss" required step="1" id="tradeStopLossInput"
                 value="{{ request('stop_loss') }}" oninput="updateSuggestedLot()"
                 class="w-full bg-slate-800 border border-rose-500/30 rounded-xl px-3 py-2.5
                        text-sm text-rose-300 focus:border-rose-500 focus:outline-none font-mono">
        </div>
      </div>

      {{-- Fase DD: Lot Disarankan -- muncul begitu Entry+SL keisi, dihitung dari Modal Trading &
           Risk% yg diatur di kartu Position Sizing atas halaman. Cuma tampil kalau sizing sudah
           diatur (capital != null) -- tanpa itu tidak ada dasar hitung, jangan tampilkan angka
           yg salah asumsi. --}}
      @if($sizing['capital'] !== null)
      <div id="suggestedLotBox" class="hidden rounded-xl border border-sky-500/30 bg-sky-500/[0.06] px-4 py-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div>
            <p class="text-[11px] text-sky-400 font-medium flex items-center gap-1">
              <x-heroicon-o-light-bulb class="w-3 h-3" /> Lot Disarankan (risk {{ $sizing['risk_pct'] }}% dari Rp{{ number_format($sizing['capital'], 0, ',', '.') }})
            </p>
            <p class="text-sm font-mono text-slate-100 mt-0.5" id="suggestedLotText">—</p>
          </div>
          <button type="button" onclick="applySuggestedLot()"
                  class="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-900 text-xs font-semibold transition">
            Pakai Ini
          </button>
        </div>
      </div>
      @endif

      {{-- Fase DE: Warning hipotetis exposure -- "kalau posisi ini ditambahkan, exposure total/
           sektor jadi berapa%". Cuma soft-warning, TIDAK memblokir submit -- keputusan tetap di
           user, sistem cuma kasih tahu. --}}
      <div id="exposureWarningBox" class="hidden rounded-xl border px-4 py-3">
        <p class="text-[11px] font-medium" id="exposureWarningTitle"></p>
        <p class="text-sm font-mono mt-0.5" id="exposureWarningText"></p>
      </div>

      {{-- Target 1 + Target 2 --}}
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs text-green-400 font-medium mb-1.5">Target 1 (2R)</label>
          <input type="number" name="target_1" required step="1"
                 value="{{ request('target_1') }}"
                 class="w-full bg-slate-800 border border-green-500/30 rounded-xl px-3 py-2.5
                        text-sm text-green-300 focus:border-green-500 focus:outline-none font-mono">
        </div>
        <div>
          <label class="block text-xs text-emerald-400 font-medium mb-1.5">
            Target 2 (3R) <span class="text-slate-500">(opsional)</span>
          </label>
          <input type="number" name="target_2" step="1"
                 value="{{ request('target_2') }}"
                 class="w-full bg-slate-800 border border-emerald-500/30 rounded-xl px-3 py-2.5
                        text-sm text-emerald-300 focus:border-emerald-500 focus:outline-none font-mono">
        </div>
      </div>

      {{-- Lot + R:R --}}
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs text-slate-400 font-medium mb-1.5">Jumlah Lot</label>
          <input type="number" name="lot" required min="1" id="tradeLotInput"
                 value="{{ request('lot') }}" oninput="updateLotHelper(); updateExposureWarning();"
                 placeholder="mis. 500"
                 class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                        text-sm text-slate-200 focus:border-sky-500 focus:outline-none font-mono">
          <p class="text-[11px] text-slate-500 mt-1" id="tradeLotHelper">
            = {{ number_format((int) request('lot', 0) * 100) }} lembar
          </p>
        </div>
        <div>
          <label class="block text-xs text-slate-400 font-medium mb-1.5">R:R Ratio</label>
          <input type="number" name="rr_ratio" step="0.1"
                 value="{{ request('rr_ratio') }}"
                 class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                        text-sm text-slate-200 focus:border-sky-500 focus:outline-none font-mono">
        </div>
      </div>

      {{-- DSS Data (hidden, pre-filled) --}}
      <input type="hidden" name="signal_quality"  value="{{ request('signal_quality') }}">
      <input type="hidden" name="dss_score"       value="{{ request('dss_score') }}">
      <input type="hidden" name="dss_prediction"  value="{{ request('dss_prediction') }}">
      <input type="hidden" name="dss_confidence"  value="{{ request('dss_confidence') }}">
      <input type="hidden" name="entry_zone_low"  value="{{ request('entry_zone_low') }}">
      <input type="hidden" name="entry_zone_high" value="{{ request('entry_zone_high') }}">

      {{-- DSS Summary (read-only display) --}}
      @if(request('dss_score'))
      <div class="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
        <p class="text-xs text-slate-500 uppercase font-medium mb-2">DSS Signal Context</p>
        <div class="flex gap-4 text-sm">
          <span class="text-slate-400">Score:
            <span class="font-bold text-slate-200">{{ request('dss_score') }}/100</span>
          </span>
          <span class="text-slate-400">Prediksi:
            <span class="font-bold text-green-400">▲ {{ strtoupper(request('dss_prediction')) }}</span>
          </span>
          <span class="text-slate-400">Confidence:
            <span class="font-bold text-sky-400">
              {{ round(request('dss_confidence') * 100) }}%
            </span>
          </span>
          <span class="text-slate-400">Kualitas:
            <span class="font-bold text-amber-400">
              {{ strtoupper(request('signal_quality')) }}
            </span>
          </span>
        </div>
      </div>
      @endif

      {{-- Notes --}}
      <div>
        <label class="block text-xs text-slate-400 font-medium mb-1.5">
          Catatan <span class="text-slate-600">(opsional)</span>
        </label>
        <textarea name="notes" rows="2" placeholder="Alasan entry, kondisi market, dll..."
                  class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                         text-sm text-slate-200 focus:border-sky-500 focus:outline-none
                         resize-none"></textarea>
      </div>

      {{-- Actions --}}
      <div class="flex gap-3 pt-2">
        <button type="submit"
                class="flex-1 py-2.5 rounded-xl bg-sky-500 hover:bg-sky-400
                       text-slate-900 font-bold text-sm transition flex items-center justify-center gap-1.5">
          <x-heroicon-o-check class="w-4 h-4" /> Simpan Trade
        </button>
        <button type="button"
                onclick="document.getElementById('addTradeModal').classList.add('hidden')"
                class="px-6 py-2.5 rounded-xl border border-slate-700 bg-slate-800
                       text-slate-400 hover:bg-slate-700 text-sm transition">
          Batal
        </button>
      </div>
    </form>
  </div>
</div>

{{-- ══════════════════════════════════════════
     CLOSE TRADE MODAL
══════════════════════════════════════════ --}}
<div id="closeTradeModal"
     class="hidden fixed inset-0 z-50 flex items-center justify-center p-4
            bg-slate-950/80 backdrop-blur-sm">
  <div class="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl">

    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-800">
      <div>
        <h2 class="font-bold text-slate-100">Tutup Trade</h2>
        <p class="text-xs text-slate-500 mt-0.5" id="closeTradeSubtitle">—</p>
      </div>
      <button onclick="document.getElementById('closeTradeModal').classList.add('hidden')"
              class="text-slate-500 hover:text-slate-300 transition text-xl">✕</button>
    </div>

    <form id="closeTradeForm" method="POST" class="p-6 space-y-4">
      @csrf

      <div>
        <label class="block text-xs text-slate-400 font-medium mb-1.5">Exit Price</label>
        <input type="number" name="exit_price" required step="1" id="closeExitPrice"
               class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                      text-sm text-slate-200 focus:border-sky-500 focus:outline-none font-mono"
               placeholder="Harga keluar aktual">
      </div>

      <div>
        <label class="block text-xs text-slate-400 font-medium mb-1.5">Hasil Trade</label>
        <select name="result" required
                class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                       text-sm text-slate-200 focus:border-sky-500 focus:outline-none">
          {{-- <option> tidak bisa memuat ikon SVG (element HTML lain di dalamnya diabaikan
               browser) -- teks polos saja, konsisten dgn elemen native form lain. --}}
          <option value="hit_target_1">Hit Target 1 (2R)</option>
          <option value="hit_target_2">Hit Target 2 (3R)</option>
          <option value="stop_loss">Stop Loss Triggered</option>
          <option value="trailing_stop">Trailing Stop (2% dari puncak)</option>
          <option value="time_target">Target Waktu (10 hari bursa)</option>
          <option value="manual_close">Manual Close (diskresi)</option>
        </select>
      </div>

      <div>
        <label class="block text-xs text-slate-400 font-medium mb-1.5">
          Catatan <span class="text-slate-600">(opsional)</span>
        </label>
        <textarea name="notes" rows="2"
                  placeholder="Kenapa close di harga ini?"
                  class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                         text-sm text-slate-200 focus:border-sky-500 focus:outline-none resize-none">
        </textarea>
      </div>

      <div class="flex gap-3 pt-1">
        <button type="submit"
                class="flex-1 py-2.5 rounded-xl bg-green-500 hover:bg-green-400
                       text-slate-900 font-bold text-sm transition">
          ✓ Tutup & Hitung PnL
        </button>
        <button type="button"
                onclick="document.getElementById('closeTradeModal').classList.add('hidden')"
                class="px-6 py-2.5 rounded-xl border border-slate-700 text-slate-400
                       hover:bg-slate-800 text-sm transition">
          Batal
        </button>
      </div>
    </form>
  </div>
</div>

@push('scripts')
<script>
function updateLotHelper() {
    const input = document.getElementById('tradeLotInput');
    const helper = document.getElementById('tradeLotHelper');
    const lot = parseInt(input.value, 10) || 0;
    helper.textContent = `= ${(lot * 100).toLocaleString('id-ID')} lembar`;
}

// Fase DD: Position Sizing Calculator. POSITION_SIZING diisi server-side (null kalau belum
// diatur -- box "Lot Disarankan" tidak dirender sama sekali di kasus itu, lihat kondisi Blade
// di atas, jadi function ini aman dipanggil kapan saja tanpa null-check berulang di tiap caller).
//
// Formula: risk_amount = capital * risk_pct / 100 (maks Rupiah yg boleh hilang kalau kena SL).
// sl_distance = entry_price - stop_loss (per lembar, HARUS > 0 -- entry di atas SL, posisi long).
// suggested_shares = floor(risk_amount / sl_distance / 100) * 100 -- dibulatkan KE BAWAH ke
// kelipatan 100 lembar (1 lot IDX = 100 lembar), supaya risk aktual TIDAK PERNAH melebihi target
// (round-down, bukan round-nearest -- lebih aman utk risk management drpd presisi).
const POSITION_SIZING = @json($sizing['capital'] !== null ? $sizing : null);

function updateSuggestedLot() {
    if (!POSITION_SIZING) return;
    const box = document.getElementById('suggestedLotBox');
    const text = document.getElementById('suggestedLotText');
    if (!box || !text) return;

    const entry = parseFloat(document.getElementById('tradeEntryPriceInput').value) || 0;
    const sl = parseFloat(document.getElementById('tradeStopLossInput').value) || 0;
    const slDistance = entry - sl;

    if (entry <= 0 || sl <= 0 || slDistance <= 0) {
        box.classList.add('hidden');
        return;
    }

    const riskAmount = POSITION_SIZING.capital * POSITION_SIZING.risk_pct / 100;
    const suggestedShares = Math.floor(riskAmount / slDistance / 100) * 100;
    const suggestedLot = suggestedShares / 100;
    const positionValue = suggestedShares * entry;

    box.classList.remove('hidden');
    if (suggestedLot < 1) {
        text.textContent = `Terlalu kecil (SL jauh dari entry) -- risk Rp${Math.round(riskAmount).toLocaleString('id-ID')} tidak cukup utk 1 lot (100 lembar) di jarak SL ini.`;
        box.dataset.lot = '';
    } else {
        text.textContent = `${suggestedLot.toLocaleString('id-ID')} lot (${suggestedShares.toLocaleString('id-ID')} lembar) ≈ Rp${Math.round(positionValue).toLocaleString('id-ID')} -- rugi maks kalau kena SL: Rp${Math.round(suggestedShares * slDistance).toLocaleString('id-ID')}`;
        box.dataset.lot = suggestedLot;
    }
}

function applySuggestedLot() {
    const box = document.getElementById('suggestedLotBox');
    if (!box || !box.dataset.lot) return;
    document.getElementById('tradeLotInput').value = box.dataset.lot;
    updateLotHelper();
}

// Fase DE: Total Exposure Warning -- kalkulator HIPOTETIS "kalau trade ini jadi ditambahkan,
// exposure total & sektor jadi berapa%". Ambang SAMA PERSIS dgn PHP (TradeController::
// EXPOSURE_WARNING_PCT dst) -- kalau salah satu diubah, ubah juga yg satu lagi.
//
// PENTING (pelajaran dari bug nyata): directive json-encode Blade SALAH HITUNG kurung kalau
// argumennya array literal nested (closure yg return array di dalam array literal lain). Aman
// cuma dipakai dgn ekspresi sederhana (variabel tunggal) -- bangun array PHP biasa dulu di
// blok terpisah, baru encode variabelnya. (Catatan meta: bahkan kata kunci Blade yg ditulis
// literal di KOMENTAR ini pun bisa ke-compile jadi directive asli -- itulah kenapa kalimat di
// atas sengaja tidak menyebut nama directive-nya secara harfiah.)
@php
    $exposureStateForJs = [
        'capital' => $sizing['capital'],
        'totalValue' => $exposure['total_value'] ?? 0,
        'bySector' => collect($exposure['by_sector'] ?? [])->mapWithKeys(fn ($s) => [$s['label'] => $s['value']]),
    ];
@endphp
const EXPOSURE_STATE = @json($exposureStateForJs);
const EXPOSURE_WARNING_PCT = 70.0;
const EXPOSURE_DANGER_PCT = 100.0;
const CONCENTRATION_WARNING_PCT = 40.0;
const CONCENTRATION_DANGER_PCT = 60.0;

function updateExposureWarning() {
    const box = document.getElementById('exposureWarningBox');
    if (!box) return;
    const titleEl = document.getElementById('exposureWarningTitle');
    const textEl = document.getElementById('exposureWarningText');

    const select = document.getElementById('tradeStockSelect');
    const opt = select?.options[select.selectedIndex];
    const sector = opt?.dataset.sector || 'Lainnya';
    const entry = parseFloat(document.getElementById('tradeEntryPriceInput')?.value) || 0;
    const lot = parseInt(document.getElementById('tradeLotInput')?.value, 10) || 0;
    const newValue = entry * lot * 100;

    if (newValue <= 0) {
        box.classList.add('hidden');
        return;
    }

    const newTotal = EXPOSURE_STATE.totalValue + newValue;
    const newSectorValue = (EXPOSURE_STATE.bySector[sector] || 0) + newValue;
    const sectorPct = newTotal > 0 ? (newSectorValue / newTotal * 100) : 0;
    const totalPct = EXPOSURE_STATE.capital ? (newTotal / EXPOSURE_STATE.capital * 100) : null;

    const totalStatus = totalPct === null ? 'unknown'
        : totalPct >= EXPOSURE_DANGER_PCT ? 'danger'
        : totalPct >= EXPOSURE_WARNING_PCT ? 'warning' : 'safe';
    const sectorStatus = sectorPct >= CONCENTRATION_DANGER_PCT ? 'danger'
        : sectorPct >= CONCENTRATION_WARNING_PCT ? 'warning' : 'safe';

    // Level tertinggi dari kedua status yg dipakai buat warna box (danger > warning > safe).
    const worst = [totalStatus, sectorStatus].includes('danger') ? 'danger'
        : [totalStatus, sectorStatus].includes('warning') ? 'warning' : 'safe';

    if (worst === 'safe') {
        box.classList.add('hidden');
        return;
    }

    box.classList.remove('hidden');
    // Emoji sengaja tidak dipakai di sini (title cuma di-set via textContent, bukan HTML) --
    // warna border/text sudah membawa sinyal urgensi, teksnya sendiri eksplisit ("PERINGATAN"/
    // "Waspada") jadi tidak butuh dekorasi tambahan.
    const styles = {
        danger: { border: 'border-rose-500/40 bg-rose-500/[0.06]', text: 'text-rose-400', title: 'PERINGATAN: Exposure Tinggi' },
        warning: { border: 'border-amber-500/30 bg-amber-500/[0.05]', text: 'text-amber-400', title: 'Waspada: Konsentrasi Naik' },
    };
    const s = styles[worst];
    box.className = `rounded-xl border px-4 py-3 ${s.border}`;
    titleEl.className = `text-[11px] font-medium ${s.text}`;
    titleEl.textContent = s.title;

    const lines = [];
    if (totalPct !== null) {
        lines.push(`Total exposure jadi Rp${Math.round(newTotal).toLocaleString('id-ID')} (${totalPct.toFixed(1)}% dari modal)`);
    }
    lines.push(`${sector}: ${sectorPct.toFixed(1)}% dari total exposure kalau posisi ini ditambahkan`);
    textEl.className = `text-sm font-mono mt-0.5 ${s.text}`;
    textEl.textContent = lines.join(' • ');
}

function openCloseModal(tradeId, stockCode, entryPrice) {
    const modal = document.getElementById('closeTradeModal');
    const form  = document.getElementById('closeTradeForm');
    const subtitle = document.getElementById('closeTradeSubtitle');

    form.action = `/trades/${tradeId}/close`;
    subtitle.textContent = `${stockCode} • Entry: ${entryPrice.toLocaleString('id-ID')}`;
    document.getElementById('closeExitPrice').value = '';

    modal.classList.remove('hidden');
}

// Fase DE: kalau modal Catat Trade Baru dibuka pre-filled (dari link sinyal DSS dgn query params
// stock_id/entry_price), langsung hitung warning-nya juga -- bukan nunggu user ngetik dulu.
if (!document.getElementById('addTradeModal').classList.contains('hidden')) {
    updateSuggestedLot();
    updateExposureWarning();
}
</script>
@endpush
</x-app-layout>
