<x-app-layout>
<div class="space-y-6"
     x-data="marketAlerts(@js($payload), @js(route('market-alerts.data')))"
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

            {{-- OWNERSHIP --}}
            <template x-if="active === 'ownership'">
              <th class="text-right font-medium px-4 py-3">Asing %</th>
            </template>
            <template x-if="active === 'ownership'">
              <th class="text-right font-medium px-4 py-3">Δ Asing (poin)</th>
            </template>

            <th class="text-right font-medium px-4 py-3">Harga</th>
            <th class="text-right font-medium px-4 py-3">%</th>
            <template x-if="active !== 'ownership'">
              <th class="text-right font-medium px-4 py-3">Nilai transaksi</th>
            </template>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/70">
          <template x-for="row in rows()" :key="row.stock_code">
            <tr class="hover:bg-slate-800/40 transition">
              <td class="px-4 py-3">
                <a :href="`/stocks/${row.stock_code}`" class="font-semibold text-slate-100 hover:text-sky-300" x-text="row.stock_code"></a>
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

              <td class="px-4 py-3 text-right font-mono text-slate-200" x-text="`Rp${fmtInt(row.close)}`"></td>
              <td class="px-4 py-3 text-right font-mono" :class="signClass(row.pct_change)" x-text="fmtPct(row.pct_change)"></td>
              <template x-if="active !== 'ownership'">
                <td class="px-4 py-3 text-right font-mono text-slate-400" x-text="fmtRp(row.value)"></td>
              </template>
            </tr>
          </template>
        </tbody>
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
function marketAlerts(payload, dataUrl) {
  return {
    payload,
    dataUrl,
    loading: false,
    active: 'volume',
    query: '',
    tabs: [
      { key: 'volume', label: 'Volume' },
      { key: 'gap', label: 'Harga & Gap' },
      { key: 'foreign', label: 'Foreign Flow' },
      { key: 'ownership', label: 'Kepemilikan' },
    ],
    init() {},
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
