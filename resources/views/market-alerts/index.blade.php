<x-app-layout>
<div class="space-y-6"
     x-data="marketAlerts(@js($payload), @js(route('market-alerts.data')), @js(route('market-alerts.foreign-history')))"
     x-init="init()">

  {{-- ── HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <p class="text-xs text-slate-500 uppercase font-medium tracking-wider">Pemantau Pasar</p>
      <h1 class="text-2xl font-bold text-slate-100 mt-0.5 flex items-center gap-2">
        <x-heroicon-o-bell-alert class="w-6 h-6" /> Market Alerts
      </h1>
      <p class="text-sm text-slate-400 mt-1">
        Volume tak wajar, gap harga, dan arus dana asing untuk seluruh saham IDX
        (<span x-text="payload.universe || 0"></span> emiten) &mdash; data akhir hari.
      </p>
    </div>
    <div class="flex items-center gap-2 text-xs text-slate-500">
      <span x-show="loading" x-cloak class="text-sky-400">Memuat&hellip;</span>
      <span>Data bursa: <span class="text-slate-300 font-mono" x-text="payload.trade_date || '—'"></span></span>
      <button type="button" @click="refresh()"
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
        Data <strong>akhir hari (EOD)</strong> dari ringkasan saham resmi IDX &mdash; <strong>bukan</strong>
        real-time, <strong>bukan</strong> data per-transaksi, dan <strong>tanpa</strong> kode broker
        (data broker/tick berbayar &amp; berlisensi). Angka arus asing dilaporkan IDX dalam
        <strong>lembar</strong>; nilai rupiah di sini perkiraan (lembar &times; harga tutup).
        Ini pemantauan deskriptif, <strong>bukan sinyal atau rekomendasi beli/jual</strong>, dan
        tidak dipakai oleh model prediksi.
      </span>
    </p>
  </div>

  {{-- ── TAB BAR ── --}}
  <div class="flex flex-wrap gap-1 border-b border-slate-800">
    <template x-for="tab in tabs" :key="tab.key">
      <button type="button" @click="active = tab.key"
              class="px-4 py-2 text-sm font-medium rounded-t-lg transition -mb-px border-b-2"
              :class="active === tab.key
                ? 'text-sky-300 border-sky-400 bg-slate-800/40'
                : 'text-slate-400 border-transparent hover:text-slate-200'">
        <span x-text="tab.label"></span>
        <span class="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400"
              x-text="(payload.counts && payload.counts[tab.key]) || 0"></span>
      </button>
    </template>
  </div>

  {{-- ── FILTER ── --}}
  <div class="flex flex-wrap items-center gap-3">
    <div class="relative">
      <input type="text" x-model="query" placeholder="Cari kode / nama saham…"
             class="text-sm bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 w-64
                    text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500">
      <svg class="w-4 h-4 text-slate-500 absolute left-2.5 top-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
      </svg>
    </div>
    <span class="text-xs text-slate-500" x-text="`${rows().length} baris`"></span>
  </div>

  {{-- Peringatan kalau data KSEI di tab ini bukan hasil impor asli --}}
  <div x-show="active === 'ownership' && (payload.ownership || []).some(r => r.source && r.source !== 'ksei_manual')"
       x-cloak
       class="text-xs text-amber-400 flex items-center gap-1.5">
    <x-heroicon-o-beaker class="w-3.5 h-3.5" />
    Data kepemilikan di tab ini <strong>contoh/sintetis</strong>, bukan file KSEI asli.
  </div>

  {{-- ── TABLES ── --}}
  <div class="glass-card rounded-2xl overflow-hidden border border-slate-800">
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-900/60 text-slate-400 text-xs uppercase tracking-wider">
          <tr>
            <th class="text-left font-medium px-4 py-3">Saham</th>

            {{-- VOLUME --}}
            <template x-if="active === 'volume'">
              <th class="text-right font-medium px-4 py-3">Volume</th>
            </template>
            <template x-if="active === 'volume'">
              <th class="text-right font-medium px-4 py-3">Rata-rata 20h</th>
            </template>
            <template x-if="active === 'volume'">
              <th class="text-right font-medium px-4 py-3">Rasio</th>
            </template>

            {{-- GAP --}}
            <template x-if="active === 'gap'">
              <th class="text-right font-medium px-4 py-3">Prev</th>
            </template>
            <template x-if="active === 'gap'">
              <th class="text-right font-medium px-4 py-3">Open</th>
            </template>
            <template x-if="active === 'gap'">
              <th class="text-right font-medium px-4 py-3">Gap</th>
            </template>

            {{-- FOREIGN --}}
            <template x-if="active === 'foreign'">
              <th class="text-right font-medium px-4 py-3">Net asing (lembar)</th>
            </template>
            <template x-if="active === 'foreign'">
              <th class="text-right font-medium px-4 py-3">Net asing (~Rp)</th>
            </template>
            <template x-if="active === 'foreign'">
              <th class="text-right font-medium px-4 py-3">% dari nilai</th>
            </template>

            {{-- OWNERSHIP (monthly KSEI -- no daily price/turnover context) --}}
            <template x-if="active === 'ownership'">
              <th class="text-right font-medium px-4 py-3">Asing %</th>
            </template>
            <template x-if="active === 'ownership'">
              <th class="text-right font-medium px-4 py-3">Δ Asing (poin)</th>
            </template>
            <template x-if="active === 'ownership'">
              <th class="text-right font-medium px-4 py-3">Snapshot</th>
            </template>

            <template x-if="active !== 'ownership'">
              <th class="text-right font-medium px-4 py-3">Harga</th>
            </template>
            <template x-if="active !== 'ownership'">
              <th class="text-right font-medium px-4 py-3">%</th>
            </template>
            <template x-if="active !== 'ownership'">
              <th class="text-right font-medium px-4 py-3">Nilai transaksi</th>
            </template>
          </tr>
        </thead>
        <template x-for="row in rows()" :key="row.stock_code">
          <tbody class="border-t border-slate-800/70">
            <tr class="hover:bg-slate-800/40 transition"
                :class="active === 'foreign' ? 'cursor-pointer' : ''"
                @click="active === 'foreign' && toggleForeignHistory(row.stock_code)">
              <td class="px-4 py-3">
                <div class="flex items-center gap-1.5">
                  <template x-if="active === 'foreign'">
                    <svg class="w-3 h-3 text-slate-500 transition-transform shrink-0"
                         :class="expandedForeign === row.stock_code ? 'rotate-90' : ''"
                         fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
                  </template>
                  <a :href="`/stocks/${row.stock_code}`" @click.stop
                     class="font-semibold text-slate-100 hover:text-sky-300" x-text="row.stock_code"></a>
                </div>
                <div class="text-[11px] text-slate-500 truncate max-w-[220px]" x-text="row.stock_name"></div>
              </td>

              {{-- VOLUME --}}
              <template x-if="active === 'volume'">
                <td class="px-4 py-3 text-right font-mono text-slate-300" x-text="fmtInt(row.volume)"></td>
              </template>
              <template x-if="active === 'volume'">
                <td class="px-4 py-3 text-right font-mono text-slate-500" x-text="fmtInt(row.avg_volume)"></td>
              </template>
              <template x-if="active === 'volume'">
                <td class="px-4 py-3 text-right font-mono font-semibold text-sky-300" x-text="`${fmtNum(row.volume_ratio)}×`"></td>
              </template>

              {{-- GAP --}}
              <template x-if="active === 'gap'">
                <td class="px-4 py-3 text-right font-mono text-slate-400" x-text="fmtInt(row.previous)"></td>
              </template>
              <template x-if="active === 'gap'">
                <td class="px-4 py-3 text-right font-mono text-slate-300" x-text="fmtInt(row.open)"></td>
              </template>
              <template x-if="active === 'gap'">
                <td class="px-4 py-3 text-right font-mono font-semibold" :class="signClass(row.gap_pct)" x-text="fmtPct(row.gap_pct)"></td>
              </template>

              {{-- FOREIGN --}}
              <template x-if="active === 'foreign'">
                <td class="px-4 py-3 text-right font-mono" :class="signClass(row.foreign_net_shares)" x-text="fmtSignedInt(row.foreign_net_shares)"></td>
              </template>
              <template x-if="active === 'foreign'">
                <td class="px-4 py-3 text-right font-mono font-semibold" :class="signClass(row.foreign_net_value)" x-text="fmtRp(row.foreign_net_value)"></td>
              </template>
              <template x-if="active === 'foreign'">
                <td class="px-4 py-3 text-right font-mono text-slate-400" x-text="row.net_ratio !== null ? `${fmtNum(row.net_ratio)}%` : '—'"></td>
              </template>

              {{-- OWNERSHIP --}}
              <template x-if="active === 'ownership'">
                <td class="px-4 py-3 text-right font-mono text-slate-300" x-text="`${fmtNum(row.foreign_pct)}%`"></td>
              </template>
              <template x-if="active === 'ownership'">
                <td class="px-4 py-3 text-right font-mono font-semibold" :class="signClass(row.foreign_pct_delta)" x-text="fmtSignedNum(row.foreign_pct_delta)"></td>
              </template>
              <template x-if="active === 'ownership'">
                <td class="px-4 py-3 text-right font-mono text-slate-500 text-xs" x-text="row.snapshot_date || '—'"></td>
              </template>

              <template x-if="active !== 'ownership'">
                <td class="px-4 py-3 text-right font-mono text-slate-200" x-text="`Rp${fmtInt(row.close)}`"></td>
              </template>
              <template x-if="active !== 'ownership'">
                <td class="px-4 py-3 text-right font-mono" :class="signClass(row.pct_change)" x-text="fmtPct(row.pct_change)"></td>
              </template>
              <template x-if="active !== 'ownership'">
                <td class="px-4 py-3 text-right font-mono text-slate-400" x-text="fmtRp(row.value)"></td>
              </template>
            </tr>

            {{-- ── EKSPANSI: riwayat arus asing per hari ── --}}
            <tr x-show="active === 'foreign' && expandedForeign === row.stock_code" x-cloak>
              <td colspan="7" class="px-4 pb-4 pt-1 bg-slate-900/50">
                <template x-if="foreignHistoryLoading === row.stock_code">
                  <div class="text-xs text-slate-500 py-3">Memuat riwayat…</div>
                </template>
                <template x-if="foreignHistoryLoading !== row.stock_code && foreignHistory[row.stock_code]">
                  <div class="space-y-2 py-2">
                    {{-- ringkasan konsistensi --}}
                    <p class="text-xs text-slate-300"
                       x-html="foreignHistorySummary(foreignHistory[row.stock_code])"></p>

                    {{-- strip bar per hari (kiri = lama, kanan = terbaru) --}}
                    <div class="flex items-end gap-[3px] h-14 overflow-x-auto">
                      <template x-for="d in foreignHistory[row.stock_code].days" :key="d.date">
                        <div class="flex flex-col items-center shrink-0" style="width: 22px"
                             :title="`${d.date}  ${fmtRp(d.net_value)}  (${fmtPct(d.pct_change)})`">
                          <div class="w-full rounded-sm"
                               :class="d.net_value > 0 ? 'bg-emerald-500/70' : (d.net_value < 0 ? 'bg-rose-500/70' : 'bg-slate-600')"
                               :style="`height: ${foreignBarHeight(d.net_value, foreignHistory[row.stock_code])}px`"></div>
                          <span class="text-[8px] text-slate-600 mt-0.5" x-text="d.date.slice(8,10)"></span>
                        </div>
                      </template>
                    </div>

                    {{-- tabel harian ringkas --}}
                    <div class="overflow-x-auto">
                      <table class="text-[11px] font-mono">
                        <thead class="text-slate-500">
                          <tr>
                            <th class="text-left pr-4 pb-1 font-medium">Tanggal</th>
                            <th class="text-right px-3 pb-1 font-medium">Net asing (~Rp)</th>
                            <th class="text-right px-3 pb-1 font-medium">% nilai</th>
                            <th class="text-right px-3 pb-1 font-medium">Harga</th>
                            <th class="text-right pl-3 pb-1 font-medium">Δ Harga</th>
                          </tr>
                        </thead>
                        <tbody>
                          <template x-for="d in [...foreignHistory[row.stock_code].days].reverse()" :key="'r'+d.date">
                            <tr>
                              <td class="text-left pr-4 py-0.5 text-slate-400" x-text="d.date"></td>
                              <td class="text-right px-3 py-0.5 font-semibold" :class="signClass(d.net_value)" x-text="fmtRp(d.net_value)"></td>
                              <td class="text-right px-3 py-0.5 text-slate-500" x-text="d.net_ratio !== null ? fmtNum(d.net_ratio) + '%' : '—'"></td>
                              <td class="text-right px-3 py-0.5 text-slate-300" x-text="`Rp${fmtInt(d.close)}`"></td>
                              <td class="text-right pl-3 py-0.5" :class="signClass(d.pct_change)" x-text="fmtPct(d.pct_change)"></td>
                            </tr>
                          </template>
                        </tbody>
                      </table>
                    </div>
                    <p class="text-[10px] text-slate-600">
                      Hijau = asing net beli hari itu, merah = net jual. Ini fakta harian, bukan sinyal.
                    </p>
                  </div>
                </template>
              </td>
            </tr>
          </tbody>
        </template>
      </table>
    </div>

    <div x-show="rows().length === 0" x-cloak class="px-4 py-12 text-center text-sm text-slate-500">
      <template x-if="active === 'ownership' && (!payload.ownership || payload.ownership.length === 0)">
        <span>Belum ada data KSEI. Jalankan <code class="text-slate-400">php artisan ksei:fetch-ownership</code> (bulanan).</span>
      </template>
      <template x-if="active !== 'ownership' || (payload.ownership && payload.ownership.length > 0)">
        <span>Tidak ada yang melewati ambang untuk tanggal ini.</span>
      </template>
    </div>
  </div>

  <p class="text-[11px] text-slate-600">
    Ambang: volume &ge; {{ config('market_alerts.volume.min_ratio') }}× rata-rata
    {{ config('market_alerts.volume_lookback') }} hari &middot;
    gap &ge; {{ config('market_alerts.gap.min_gap_pct') }}% atau gerak &ge; {{ config('market_alerts.gap.min_move_pct') }}% &middot;
    net asing &ge; Rp {{ number_format(config('market_alerts.foreign.min_net_value_rp') / 1_000_000_000, 0) }} M.
    Diperbarui otomatis tiap sore setelah IDX rilis (&plusmn;18:05 WIB).
  </p>
</div>

<script>
function marketAlerts(payload, dataUrl, foreignHistoryUrl) {
  return {
    payload,
    dataUrl,
    foreignHistoryUrl,
    loading: false,
    active: 'volume',
    query: '',
    expandedForeign: null,
    foreignHistory: {},
    foreignHistoryLoading: null,
    tabs: [
      { key: 'volume', label: 'Volume' },
      { key: 'gap', label: 'Harga & Gap' },
      { key: 'foreign', label: 'Foreign Flow' },
      { key: 'ownership', label: 'Kepemilikan' },
    ],
    init() {},

    async toggleForeignHistory(code) {
      if (this.expandedForeign === code) { this.expandedForeign = null; return; }
      this.expandedForeign = code;
      if (this.foreignHistory[code]) return;
      this.foreignHistoryLoading = code;
      try {
        const res = await fetch(`${this.foreignHistoryUrl}?code=${encodeURIComponent(code)}&days=20`,
          { headers: { 'Accept': 'application/json' } });
        if (res.ok) this.foreignHistory[code] = await res.json();
      } finally {
        this.foreignHistoryLoading = null;
      }
    },
    foreignBarHeight(v, hist) {
      const max = Math.max(...hist.days.map(d => Math.abs(d.net_value)), 1);
      return Math.max(2, Math.round(Math.abs(v) / max * 44));
    },
    foreignHistorySummary(hist) {
      const s = hist.summary;
      if (!s) return 'Belum ada riwayat.';
      const net = this.fmtRp(s.net_total_value);
      const netCls = s.net_total_value > 0 ? 'text-emerald-400' : (s.net_total_value < 0 ? 'text-rose-400' : 'text-slate-400');
      let streak = '';
      if (s.streak >= 2) {
        const word = s.streak_dir === 'buy' ? 'net beli' : 'net jual';
        const cls = s.streak_dir === 'buy' ? 'text-emerald-400' : 'text-rose-400';
        streak = ` &middot; <span class="${cls}">${s.streak} hari beruntun ${word}</span>`;
      }
      return `${s.window} hari terakhir: <span class="text-emerald-400">${s.buy_days} hari</span> asing net beli, `
        + `<span class="text-rose-400">${s.sell_days} hari</span> net jual &middot; `
        + `total <span class="${netCls} font-semibold">${net}</span>${streak}`;
    },
    rows() {
      const list = this.payload[this.active] || [];
      const q = this.query.trim().toLowerCase();
      if (!q) return list;
      return list.filter(r =>
        (r.stock_code || '').toLowerCase().includes(q) ||
        (r.stock_name || '').toLowerCase().includes(q));
    },
    async refresh() {
      this.loading = true;
      try {
        const res = await fetch(this.dataUrl + '?fresh=1', { headers: { 'Accept': 'application/json' } });
        if (res.ok) this.payload = await res.json();
      } finally {
        this.loading = false;
      }
    },
    fmtNum(v, d = 2) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      return Number(v).toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: d });
    },
    fmtInt(v) { return this.fmtNum(v, 0); },
    fmtSignedInt(v) {
      if (v === null || v === undefined) return '—';
      return (v > 0 ? '+' : '') + this.fmtInt(v);
    },
    fmtSignedNum(v) {
      if (v === null || v === undefined) return '—';
      return (v > 0 ? '+' : '') + this.fmtNum(v);
    },
    fmtPct(v) {
      if (v === null || v === undefined) return '—';
      return (v > 0 ? '+' : '') + this.fmtNum(v, 2) + '%';
    },
    fmtRp(v) {
      if (v === null || v === undefined || v === 0) return v === 0 ? 'Rp0' : '—';
      const abs = Math.abs(v);
      const sign = v < 0 ? '−' : '';
      if (abs >= 1e12) return `${sign}Rp${this.fmtNum(abs / 1e12, 2)} T`;
      if (abs >= 1e9)  return `${sign}Rp${this.fmtNum(abs / 1e9, 2)} M`;
      if (abs >= 1e6)  return `${sign}Rp${this.fmtNum(abs / 1e6, 1)} jt`;
      return `${sign}Rp${this.fmtInt(abs)}`;
    },
    signClass(v) {
      if (v === null || v === undefined || v === 0) return 'text-slate-400';
      return v > 0 ? 'text-emerald-400' : 'text-rose-400';
    },
  };
}
</script>
</x-app-layout>
