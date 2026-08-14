<x-app-layout>
<div class="space-y-6">

  {{-- ── HEADER ── --}}
  <div class="flex items-center justify-between">
    <div>
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Portfolio Tracker</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5">Trade Journal</h1>
      <p class="text-sm text-slate-400 mt-1">Rekam jejak sinyal DSS vs hasil aktual pasar</p>
      {{-- Fase CA: dulu kartu ringkasan mencampur GABUNGAN + 2 aturan lama yang TERBUKTI
           tumpang tindih periode untuk saham sama (dicek dari notes backfill sendiri) --
           sekarang cuma GABUNGAN yang resmi, sisanya di bagian "Strategi Lain" di bawah. --}}
      <p class="text-[11px] text-sky-400/80 mt-1">
        📊 Kartu di bawah = <b>strategi resmi GABUNGAN</b> saja (ret_2d≤-5% atau drawdown≤-20%)
      </p>
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
      <p class="text-2xl font-bold
        {{ $stats['total_pnl'] >= 0 ? 'text-green-400' : 'text-rose-400' }}">
        {{ $stats['total_pnl'] >= 0 ? '+' : '' }}Rp {{ number_format($stats['total_pnl'], 0, ',', '.') }}
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

  {{-- ── STRATEGI LAIN (arsip, TIDAK dihitung ke kartu resmi di atas) ── --}}
  @if(!empty($strategyBreakdown))
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
      📁 Strategi Lain (di luar GABUNGAN — arsip riset, bukan angka resmi)
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
      </div>
      @endforeach
    </div>
  </div>
  @endif

  {{-- ── OPEN POSITIONS ── --}}
  @if($open->count() > 0)
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
      🟢 Posisi Terbuka ({{ $open->count() }})
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
            <div class="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/20
                        flex items-center justify-center font-bold text-sky-400 text-sm">
              {{ $trade->stock->code }}
            </div>
            <div>
              <p class="font-semibold text-slate-100">{{ $trade->stock->code }}</p>
              <p class="text-[11px] text-slate-400">
                {{ $trade->stock->company_name }} • Masuk
                {{-- entry_date cuma tanggal (selalu 00:00:00, lihat catatan whereDate() di
                     DetectDrawdownBounceSignalCommand) -- created_at yang punya jam presisi,
                     dan untuk trade yang disinkron otomatis (SYNC_OPEN) ini SAMA PERSIS dengan
                     jam signal terdeteksi/terdaftar (dicek: 15:18 WIB, jam job harian). Beda dari
                     jam "harga HH:MM WIB" di footer kartu -- itu jam quote LIVE, bukan jam masuk. --}}
                {{ $trade->created_at->timezone('Asia/Jakarta')->format('d M Y, H:i') }} WIB
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

  {{-- ── CLOSED TRADES ── --}}
  <div>
    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
      📋 Riwayat Trading ({{ $closed->count() }})
    </h2>

    @if($closed->count() > 0)
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
            @foreach($closed as $trade)
            <tr class="hover:bg-slate-800/30 transition">
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-slate-100">{{ $trade->stock->code }}</span>
                  <span class="text-[10px] text-slate-500">
                    {{ strtoupper($trade->signal_quality ?? '') }}
                  </span>
                </div>
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

  {{-- ── EMPTY STATE (no trades at all) ── --}}
  @if($stats['total'] === 0)
  <div class="glass-card border border-slate-800/80 rounded-2xl p-12 text-center">
    <div class="text-5xl mb-4">📊</div>
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
        <h2 class="font-bold text-slate-100">📝 Catat Trade Baru</h2>
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
          <select name="stock_id" required
                  class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                         text-sm text-slate-200 focus:border-sky-500 focus:outline-none">
            @foreach(\App\Models\Stock::where('is_active',true)->orderBy('code')->get() as $s)
              <option value="{{ $s->id }}"
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
          <input type="number" name="entry_price" required step="1"
                 value="{{ request('entry_price') }}"
                 class="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5
                        text-sm text-slate-200 focus:border-sky-500 focus:outline-none font-mono">
        </div>
        <div>
          <label class="block text-xs text-rose-400 font-medium mb-1.5">Stop Loss</label>
          <input type="number" name="stop_loss" required step="1"
                 value="{{ request('stop_loss') }}"
                 class="w-full bg-slate-800 border border-rose-500/30 rounded-xl px-3 py-2.5
                        text-sm text-rose-300 focus:border-rose-500 focus:outline-none font-mono">
        </div>
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
                 value="{{ request('lot') }}" oninput="updateLotHelper()"
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
                       text-slate-900 font-bold text-sm transition">
          💾 Simpan Trade
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
          <option value="hit_target_1">✅ Hit Target 1 (2R)</option>
          <option value="hit_target_2">✅ Hit Target 2 (3R)</option>
          <option value="stop_loss">❌ Stop Loss Triggered</option>
          <option value="manual_close">📌 Manual Close</option>
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

function openCloseModal(tradeId, stockCode, entryPrice) {
    const modal = document.getElementById('closeTradeModal');
    const form  = document.getElementById('closeTradeForm');
    const subtitle = document.getElementById('closeTradeSubtitle');

    form.action = `/trades/${tradeId}/close`;
    subtitle.textContent = `${stockCode} • Entry: ${entryPrice.toLocaleString('id-ID')}`;
    document.getElementById('closeExitPrice').value = '';

    modal.classList.remove('hidden');
}
</script>
@endpush

</x-app-layout>
