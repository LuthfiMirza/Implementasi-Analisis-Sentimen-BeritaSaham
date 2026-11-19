<x-app-layout>
@php
  $strategyConfig = match($trade->strategy_label) {
    'gabungan'              => ['bg-sky-500/10 text-sky-400 border-sky-500/30', 'GABUNGAN'],
    'momentum'              => ['bg-amber-500/10 text-amber-400 border-amber-500/30', 'MOMENTUM'],
    'ai_tp30'               => ['bg-purple-500/10 text-purple-400 border-purple-500/30', 'AI TP30'],
    'legacy_stock_only'     => ['bg-slate-700/40 text-slate-400 border-slate-600/60', 'LAMA: STOCK-ONLY'],
    'legacy_ab_ac'          => ['bg-slate-700/40 text-slate-400 border-slate-600/60', 'LAMA: AB/AC'],
    'manual_discretionary'  => ['bg-slate-700/40 text-slate-300 border-slate-600/60', 'MANUAL'],
    'bottom_rebound'        => ['bg-emerald-500/10 text-emerald-400 border-emerald-500/30', 'BOTTOM-REBOUND'],
    'bottom_to_top'         => ['bg-indigo-500/10 text-indigo-400 border-indigo-500/30', 'BOTTOM-TO-TOP'],
    'bsjp'                  => ['bg-emerald-500/10 text-emerald-400 border-emerald-500/30', 'BSJP MOMENTUM'],
    default                 => ['bg-slate-800 text-slate-400 border-slate-700', strtoupper((string) ($trade->strategy_label ?? 'TRADE'))],
  };

  $gradeBadge = match(strtoupper(trim((string) $trade->signal_quality))) {
    'A+' => 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    'A'  => 'bg-sky-500/20 text-sky-300 border-sky-500/40',
    'B'  => 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    'C'  => 'bg-rose-500/20 text-rose-300 border-rose-500/40',
    default => 'bg-slate-800 text-slate-400 border-slate-700',
  };

  $snapshot = is_array($trade->indicators_snapshot) ? $trade->indicators_snapshot : [];
  $ticker = strtoupper((string) ($trade->stock?->code ?? $trade->ticker));
  $isOpen = $trade->status === 'open';
@endphp

<div class="space-y-5"
     x-data="tradeDetailChart({
       tradeId: {{ $trade->id }},
       ticker: '{{ $ticker }}',
       isOpen: {{ $isOpen ? 'true' : 'false' }},
       chartDataUrl: '{{ route('trades.chart-data', $trade) }}',
       quoteUrl: '{{ url('/api/stocks/' . $ticker . '/quote') }}',
       initialPayload: @js($initialChart)
     })"
     x-init="init()">

  {{-- ── TOP NAVIGATION & HEADER ── --}}
  <div class="flex flex-wrap items-center justify-between gap-4">
    <div class="flex items-center gap-3">
      <a href="{{ route('trades.index') }}"
         class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition">
        ← Kembali ke Jurnal
      </a>

      <div class="flex items-center gap-3">
        @if($trade->stock?->logo_url)
          <img src="{{ $trade->stock->logo_url }}" alt="{{ $ticker }}"
               class="w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 object-contain p-1"
               onerror="this.style.display='none'">
        @endif
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="text-xl font-bold text-slate-100 tracking-tight">{{ $ticker }}</h1>
            <span class="px-2 py-0.5 text-[11px] font-semibold rounded-md border {{ $strategyConfig[0] }}">
              {{ $strategyConfig[1] }}
            </span>
            @if($trade->signal_quality)
              <span class="px-2 py-0.5 text-[11px] font-bold rounded-md border {{ $gradeBadge }}">
                GRADE {{ strtoupper((string) $trade->signal_quality) }}
              </span>
            @endif
            @if($isOpen)
              <span class="inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-semibold rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                OPEN • <span x-text="liveStatusText"></span>
              </span>
            @else
              <span class="px-2 py-0.5 text-[11px] font-semibold rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                CLOSED ({{ strtoupper(str_replace('_', ' ', (string) $trade->result)) }})
              </span>
            @endif
          </div>
          <p class="text-xs text-slate-400 mt-0.5">
            {{ $trade->stock?->company_name ?? $ticker }} • Trade #{{ $trade->id }} • Entry {{ $trade->entry_date?->timezone('Asia/Jakarta')->format('d M Y') }}
          </p>
        </div>
      </div>
    </div>

    {{-- Timeframe Switcher --}}
    <div class="flex items-center gap-2">
      <div class="inline-flex rounded-xl bg-slate-900/90 border border-slate-700/80 p-1">
        <button type="button"
                @click="switchTimeframe('15m')"
                :disabled="!hasIntraday || loading"
                :class="timeframe === '15m'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                  : (hasIntraday ? 'text-slate-400 hover:text-slate-200 border border-transparent' : 'text-slate-600 cursor-not-allowed border border-transparent')"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold transition">
          15m Intraday
        </button>
        <button type="button"
                @click="switchTimeframe('1d')"
                :disabled="loading"
                :class="timeframe === '1d'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                  : 'text-slate-400 hover:text-slate-200 border border-transparent'"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold transition">
          1D Harian
        </button>
      </div>

      @if($isOpen)
        <button type="button"
                @click="showCloseModal = true"
                class="px-3.5 py-2 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-300 text-xs font-semibold transition">
          Tutup Posisi
        </button>
      @endif
    </div>
  </div>

  {{-- Fallback notice if intraday missing --}}
  <template x-if="fallbackNotice">
    <div class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-200">
      ⚠️ Data bar 15-menit tidak tersedia untuk rentang tanggal trade ini, otomatis menampilkan chart <strong>1D Harian</strong>.
    </div>
  </template>

  {{-- ── 5 METRIC SUMMARY CARDS ── --}}
  <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
    {{-- 1. Harga Live / Exit & PnL --}}
    <div class="glass-card rounded-2xl p-3.5 border border-slate-800">
      <p class="text-[11px] text-slate-400 uppercase tracking-wider font-medium">
        {{ $isOpen ? 'Harga Live' : 'Harga Exit' }}
      </p>
      <p class="text-xl font-bold text-slate-100 mt-1" x-text="'Rp ' + formatNum(displayPrice)"></p>
      <p class="text-xs font-semibold mt-0.5"
         :class="displayPnlPct >= 0 ? 'text-emerald-400' : 'text-rose-400'">
        <span x-text="(displayPnlPct >= 0 ? '+' : '') + displayPnlPct.toFixed(2) + '%'"></span>
        <span class="text-slate-400 font-normal" x-text="' (' + (displayPnlRp >= 0 ? '+' : '-') + 'Rp ' + formatNum(Math.abs(displayPnlRp)) + ')'"></span>
      </p>
    </div>

    {{-- 2. Entry & Ukuran Posisi --}}
    <div class="glass-card rounded-2xl p-3.5 border border-sky-500/20">
      <p class="text-[11px] text-sky-400 uppercase tracking-wider font-medium">Entry & Posisi</p>
      <p class="text-xl font-bold text-slate-100 mt-1">Rp {{ number_format((float) $trade->entry_price, 0, ',', '.') }}</p>
      <p class="text-xs text-slate-400 mt-0.5">
        {{ number_format((int) $trade->lot_size / 100) }} Lot • Rp {{ number_format((float) $trade->position_value, 0, ',', '.') }}
      </p>
    </div>

    {{-- 3. Hard Stop Loss --}}
    <div class="glass-card rounded-2xl p-3.5 border border-rose-500/20">
      <p class="text-[11px] text-rose-400 uppercase tracking-wider font-medium">Hard Stop Loss</p>
      <p class="text-xl font-bold text-rose-300 mt-1" x-text="'Rp ' + formatNum(levels.stop_loss)"></p>
      <p class="text-xs text-slate-400 mt-0.5">
        <span x-text="levels.sl_pct.toFixed(2) + '% dari entry'"></span>
        <span x-show="distanceToSlPct !== null" class="text-slate-300" x-text="' • Jarak ' + distanceToSlPct.toFixed(2) + '%'"></span>
      </p>
    </div>

    {{-- 4. Peak (MFE) & Dynamic Trailing Stop --}}
    <div class="glass-card rounded-2xl p-3.5 border border-amber-500/20">
      <p class="text-[11px] text-amber-400 uppercase tracking-wider font-medium">Peak & Trailing Stop</p>
      <p class="text-xl font-bold text-amber-300 mt-1"
         x-text="levels.trailing_active ? ('Rp ' + formatNum(levels.trailing_stop)) : 'Belum Aktif'"></p>
      <p class="text-xs text-slate-400 mt-0.5">
        Peak: <span class="text-slate-200 font-medium" x-text="'Rp ' + formatNum(levels.peak_price)"></span>
        <span class="text-emerald-400" x-text="' (+' + levels.mfe_pct.toFixed(2) + '%)'"></span>
      </p>
    </div>

    {{-- 5. Target Profit --}}
    <div class="glass-card rounded-2xl p-3.5 border border-emerald-500/20">
      <p class="text-[11px] text-emerald-400 uppercase tracking-wider font-medium">Target Profit</p>
      <p class="text-xl font-bold text-emerald-300 mt-1" x-text="'Rp ' + formatNum(levels.target_1)"></p>
      <p class="text-xs text-slate-400 mt-0.5">
        <span x-text="'TP1 +' + levels.tp1_pct.toFixed(1) + '%'"></span>
        <template x-if="levels.target_2">
          <span x-text="' • TP2 Rp ' + formatNum(levels.target_2)"></span>
        </template>
      </p>
    </div>
  </div>

  {{-- ── INTERACTIVE 3-PANE STRATEGY CHART ── --}}
  <div class="glass-card rounded-2xl border border-slate-800 overflow-hidden">
    {{-- Chart Legend & Live Crosshair Readout --}}
    <div class="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 bg-slate-900/70 border-b border-slate-800 text-xs">
      <div class="flex flex-wrap items-center gap-3">
        <span class="font-bold text-slate-200">{{ $ticker }}</span>
        <span class="text-slate-400" x-text="timeframe === '15m' ? '15 Menit (WIB)' : 'Harian (1D)'"></span>
        <span class="inline-flex items-center gap-1 text-sky-400"><span class="w-3 h-0.5 bg-sky-400 inline-block"></span>Entry</span>
        <span class="inline-flex items-center gap-1 text-rose-400"><span class="w-3 h-0.5 bg-rose-400 inline-block"></span>Hard SL</span>
        <span class="inline-flex items-center gap-1 text-emerald-400"><span class="w-3 h-0.5 bg-emerald-400 inline-block"></span>TP</span>
        <span class="inline-flex items-center gap-1 text-amber-400"><span class="w-3 h-0.5 bg-amber-400 inline-block"></span>Trailing Stop / MA20</span>
        <span class="inline-flex items-center gap-1 text-amber-300/80"><span class="w-2 h-2 rounded-sm bg-amber-400/80 inline-block"></span>Vol Spike ≥1.5x</span>
      </div>
      <div class="flex items-center gap-3 font-mono text-[11px] text-slate-300" x-show="hoverInfo">
        <span x-text="hoverInfo"></span>
      </div>
    </div>

    {{-- Pane 1: Main Candlestick + Strategy Lines + Volume --}}
    <div class="relative" style="min-height: 400px; background: #0b1120;">
      <div x-show="loading"
           class="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/60 text-xs text-slate-300">
        Memuat data chart...
      </div>
      <div x-show="chartError" x-cloak
           class="absolute inset-0 z-10 flex items-center justify-center p-4 text-xs text-rose-300 bg-slate-950/80"
           x-text="chartError"></div>
      <div id="tradeMainChart" style="width: 100%; height: 400px;"></div>
    </div>

    {{-- Pane 2: RSI(14) --}}
    <div class="border-t border-slate-800/90" style="background: #0b1120;">
      <div class="flex items-center justify-between px-4 py-1 bg-slate-900/50 text-[11px]">
        <span class="font-semibold text-violet-300">RSI (14) Wilder</span>
        <span class="text-slate-500">Oversold: 30 • Momentum: 60</span>
      </div>
      <div id="tradeRsiChart" style="width: 100%; height: 135px;"></div>
    </div>

    {{-- Pane 3: MACD (12, 26, 9) --}}
    <div class="border-t border-slate-800/90" style="background: #0b1120;">
      <div class="flex items-center justify-between px-4 py-1 bg-slate-900/50 text-[11px]">
        <span class="font-semibold text-sky-300">MACD (12, 26, 9)</span>
        <span class="text-slate-500">
          <span class="text-sky-400">MACD</span> • <span class="text-orange-400">Signal</span> • Histogram
        </span>
      </div>
      <div id="tradeMacdChart" style="width: 100%; height: 135px;"></div>
    </div>
  </div>

  {{-- ── STRATEGY AUDIT & NOTES CARD ── --}}
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <div class="glass-card rounded-2xl p-4 border border-slate-800 space-y-3">
      <h2 class="text-sm font-bold text-slate-200 flex items-center gap-2">
        🛡️ Protokol Strategi & Audit Sinyal
      </h2>
      <div class="grid grid-cols-2 gap-2.5 text-xs">
        <div class="rounded-xl bg-slate-900/70 border border-slate-800 p-2.5">
          <p class="text-slate-500 text-[11px]">Aturan Trailing Stop</p>
          <p class="text-slate-200 font-semibold mt-0.5"
             x-text="'Pullback ' + levels.trailing_pullback_pct + '% (aktif saat profit ≥ +' + levels.trailing_activation_pct + '%)'"></p>
        </div>
        <div class="rounded-xl bg-slate-900/70 border border-slate-800 p-2.5">
          <p class="text-slate-500 text-[11px]">Grade & Skor DSS</p>
          <p class="text-slate-200 font-semibold mt-0.5">
            {{ strtoupper((string) ($trade->signal_quality ?? '—')) }}
            @if($trade->dss_score)
              (Skor {{ number_format((float) $trade->dss_score, 0) }})
            @endif
          </p>
        </div>
        <div class="rounded-xl bg-slate-900/70 border border-slate-800 p-2.5">
          <p class="text-slate-500 text-[11px]">Vol Ratio / Lower Wick</p>
          <p class="text-slate-200 font-semibold mt-0.5">
            {{ isset($snapshot['vol_ratio_ma20']) ? number_format((float) $snapshot['vol_ratio_ma20'], 2) . 'x' : (isset($snapshot['vol_ratio']) ? number_format((float) $snapshot['vol_ratio'], 2) . 'x' : '—') }}
            /
            {{ isset($snapshot['lower_wick_pct']) ? number_format((float) $snapshot['lower_wick_pct'], 2) . '%' : '—' }}
          </p>
        </div>
        <div class="rounded-xl bg-slate-900/70 border border-slate-800 p-2.5">
          <p class="text-slate-500 text-[11px]">Holding Days / Exit</p>
          <p class="text-slate-200 font-semibold mt-0.5">
            {{ $trade->holding_days !== null ? $trade->holding_days . ' hari' : 'Berjalan' }}
            @if($trade->closed_at)
              • {{ $trade->closed_at->timezone('Asia/Jakarta')->format('d M Y H:i') }} WIB
            @endif
          </p>
        </div>
      </div>
    </div>

    <div class="glass-card rounded-2xl p-4 border border-slate-800 space-y-2.5">
      <h2 class="text-sm font-bold text-slate-200">📝 Catatan Eksekusi Trade</h2>
      <p class="text-xs text-slate-300 leading-relaxed whitespace-pre-line">
        {{ $trade->notes ?: 'Belum ada catatan khusus untuk trade ini.' }}
      </p>
      @if(!empty($snapshot))
        <div class="pt-2 border-t border-slate-800 flex flex-wrap gap-1.5">
          @foreach($snapshot as $k => $v)
            @if(is_scalar($v))
              <span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-[10px] text-slate-400 font-mono">
                {{ $k }}: <strong class="text-slate-200">{{ $v }}</strong>
              </span>
            @endif
          @endforeach
        </div>
      @endif
    </div>
  </div>

  {{-- ── QUICK CLOSE MODAL (ONLY IF OPEN) ── --}}
  @if($isOpen)
    <div x-show="showCloseModal" x-cloak
         class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-xs p-4">
      <div @click.away="showCloseModal = false"
           class="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700 p-5 space-y-4 shadow-2xl">
        <div class="flex items-center justify-between">
          <h3 class="text-base font-bold text-slate-100">Tutup Posisi {{ $ticker }}</h3>
          <button type="button" @click="showCloseModal = false" class="text-slate-400 hover:text-slate-200">✕</button>
        </div>
        <form method="POST" action="{{ route('trades.close', $trade) }}" class="space-y-3">
          @csrf
          <div>
            <label class="block text-xs text-slate-400 mb-1">Harga Exit (Rp)</label>
            <input type="number" step="0.01" name="exit_price" required
                   :value="displayPrice"
                   class="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100">
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Alasan Exit</label>
            <select name="result" required
                    class="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100">
              <option value="trailing_stop">Trailing Stop</option>
              <option value="hit_target_1">Hit Target 1 (TP1)</option>
              <option value="hit_target_2">Hit Target 2 (TP2)</option>
              <option value="stop_loss">Stop Loss (SL)</option>
              <option value="time_target">Target Waktu (10 Hari)</option>
              <option value="manual_close">Manual Close</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Catatan (Opsional)</label>
            <input type="text" name="notes" placeholder="Catatan penutupan..."
                   class="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100">
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" @click="showCloseModal = false"
                    class="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold">Batal</button>
            <button type="submit"
                    class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold">Simpan & Tutup</button>
          </div>
        </form>
      </div>
    </div>
  @endif
</div>

<script src="{{ asset('vendor/lightweight-charts.standalone.production.js') }}"></script>
<script>
function tradeDetailChart(cfg) {
  return {
    tradeId: cfg.tradeId,
    ticker: cfg.ticker,
    isOpen: cfg.isOpen,
    chartDataUrl: cfg.chartDataUrl,
    quoteUrl: cfg.quoteUrl,
    payload: cfg.initialPayload,
    timeframe: cfg.initialPayload.timeframe || '1d',
    hasIntraday: !!cfg.initialPayload.has_intraday,
    fallbackNotice: !!cfg.initialPayload.fallback_to_daily,
    levels: cfg.initialPayload.levels,
    loading: false,
    chartError: null,
    showCloseModal: false,
    hoverInfo: '',
    liveStatusText: 'Menunggu quote...',
    livePrice: null,
    pollTimer: null,
    resizeHandler: null,

    // Chart instances
    mainChart: null,
    rsiChart: null,
    macdChart: null,
    candleSeries: null,
    trailingLineRef: null,

    get displayPrice() {
      if (this.isOpen) {
        if (this.livePrice && this.livePrice > 0) return this.livePrice;
        return this.payload.last_bar ? this.payload.last_bar.close : this.payload.trade.entry_price;
      }
      return this.payload.trade.exit_price || this.payload.trade.entry_price;
    },

    get displayPnlPct() {
      if (!this.isOpen && this.payload.trade.pnl_percent !== null) {
        return Number(this.payload.trade.pnl_percent);
      }
      const entry = Number(this.payload.trade.entry_price || 0);
      if (entry <= 0) return 0;
      return ((this.displayPrice - entry) / entry) * 100;
    },

    get displayPnlRp() {
      if (!this.isOpen && this.payload.trade.pnl_total !== null) {
        return Number(this.payload.trade.pnl_total);
      }
      const entry = Number(this.payload.trade.entry_price || 0);
      const shares = Number(this.payload.trade.lot_size || 0);
      return (this.displayPrice - entry) * shares;
    },

    get distanceToSlPct() {
      const p = Number(this.displayPrice || 0);
      const sl = Number(this.levels?.stop_loss || 0);
      if (p <= 0 || sl <= 0) return null;
      return ((sl - p) / p) * 100;
    },

    formatNum(v) {
      if (v === null || v === undefined || isNaN(v)) return '0';
      return Math.round(Number(v)).toLocaleString('id-ID');
    },

    init() {
      this.$nextTick(() => {
        this.renderCharts();
        if (this.isOpen) {
          this.fetchLiveQuote();
          this.pollTimer = setInterval(() => this.fetchLiveQuote(), 15000);
        }
      });
    },

    async switchTimeframe(tf) {
      if (this.loading || (tf === '15m' && !this.hasIntraday)) return;
      this.loading = true;
      try {
        const res = await fetch(`${this.chartDataUrl}?tf=${tf}`, { headers: { 'Accept': 'application/json' } });
        if (!res.ok) return;
        const data = await res.json();
        this.payload = data;
        this.timeframe = data.timeframe;
        this.levels = data.levels;
        this.fallbackNotice = !!data.fallback_to_daily;
        this.destroyCharts();
        this.$nextTick(() => this.renderCharts());
      } catch (e) {
        console.error('Failed to switch timeframe:', e);
      } finally {
        this.loading = false;
      }
    },

    destroyCharts() {
      if (this.resizeHandler) {
        window.removeEventListener('resize', this.resizeHandler);
        this.resizeHandler = null;
      }
      if (this.mainChart) { this.mainChart.remove(); this.mainChart = null; }
      if (this.rsiChart) { this.rsiChart.remove(); this.rsiChart = null; }
      if (this.macdChart) { this.macdChart.remove(); this.macdChart = null; }
      this.candleSeries = null;
      this.trailingLineRef = null;
    },

    renderCharts(attempt = 0) {
      if (typeof LightweightCharts === 'undefined') {
        if (attempt < 20) {
          setTimeout(() => this.renderCharts(attempt + 1), 150);
        } else {
          this.chartError = 'Library chart gagal dimuat. Coba refresh halaman (Cmd+Shift+R).';
        }
        return;
      }

      const mainEl = document.getElementById('tradeMainChart');
      const rsiEl = document.getElementById('tradeRsiChart');
      const macdEl = document.getElementById('tradeMacdChart');
      if (!mainEl || !rsiEl || !macdEl) return;

      this.chartError = null;
      const chartWidth = mainEl.clientWidth || mainEl.parentElement?.clientWidth || 900;

      try {
        const isIntraday = this.timeframe === '15m';
        const baseOptions = {
          layout: {
            background: { type: 'solid', color: '#0b1120' },
            textColor: '#94a3b8',
            fontSize: 11,
          },
          grid: {
            vertLines: { color: 'rgba(51, 65, 85, 0.25)' },
            horzLines: { color: 'rgba(51, 65, 85, 0.25)' },
          },
          crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: { color: 'rgba(148, 163, 184, 0.4)', style: LightweightCharts.LineStyle.Dashed },
            horzLine: { color: 'rgba(148, 163, 184, 0.4)', style: LightweightCharts.LineStyle.Dashed },
          },
          rightPriceScale: {
            borderColor: 'rgba(51, 65, 85, 0.6)',
          },
          timeScale: {
            borderColor: 'rgba(51, 65, 85, 0.6)',
            timeVisible: isIntraday,
            secondsVisible: false,
          },
        };

        // 1. Main Candlestick Chart
        this.mainChart = LightweightCharts.createChart(mainEl, {
          ...baseOptions,
          width: chartWidth,
          height: mainEl.clientHeight || 400,
        });

        this.candleSeries = this.mainChart.addCandlestickSeries({
          upColor: '#10b981',
          downColor: '#f43f5e',
          borderVisible: false,
          wickUpColor: '#10b981',
          wickDownColor: '#f43f5e',
        });
        this.candleSeries.setData(this.payload.candles || []);

        // Markers (BUY, PEAK, EXIT)
        if (Array.isArray(this.payload.markers) && this.payload.markers.length > 0) {
          this.candleSeries.setMarkers(this.payload.markers);
        }

        // Volume Histogram overlay at bottom 20%
        const volSeries = this.mainChart.addHistogramSeries({
          priceFormat: { type: 'volume' },
          priceScaleId: '',
        });
        volSeries.priceScale().applyOptions({
          scaleMargins: { top: 0.80, bottom: 0 },
        });
        volSeries.setData(this.payload.volume || []);

        // MA20 Line
        if (Array.isArray(this.payload.ma20) && this.payload.ma20.length > 0) {
          const ma20Series = this.mainChart.addLineSeries({
            color: '#f59e0b',
            lineWidth: 1.5,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          ma20Series.setData(this.payload.ma20);
        }

        // Strategy-specific overlays
        const strat = (this.payload.trade.strategy_label || '').toLowerCase();
        if (strat === 'bottom_to_top' && Array.isArray(this.payload.bb_lower) && this.payload.bb_lower.length > 0) {
          const bbUpper = this.mainChart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.45)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          const bbLower = this.mainChart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.75)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          bbUpper.setData(this.payload.bb_upper || []);
          bbLower.setData(this.payload.bb_lower || []);
        } else if (['gabungan', 'bottom_rebound'].includes(strat) && Array.isArray(this.payload.high20) && this.payload.high20.length > 0) {
          const high20Series = this.mainChart.addLineSeries({
            color: 'rgba(148, 163, 184, 0.45)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          high20Series.setData(this.payload.high20);
        }

        // Horizontal Price Lines (Entry, Hard SL, TP1, TP2, Trailing Stop)
        this.drawStrategyPriceLines();

        // 2. RSI(14) Chart
        this.rsiChart = LightweightCharts.createChart(rsiEl, {
          ...baseOptions,
          width: rsiEl.clientWidth || chartWidth,
          height: rsiEl.clientHeight || 135,
        });
        const rsiSeries = this.rsiChart.addLineSeries({
          color: '#a78bfa',
          lineWidth: 2,
          priceLineVisible: false,
        });
        rsiSeries.setData(this.payload.rsi14 || []);
        rsiSeries.createPriceLine({ price: 60, color: 'rgba(16, 185, 129, 0.45)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '60' });
        rsiSeries.createPriceLine({ price: 30, color: 'rgba(244, 63, 94, 0.55)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '30' });

        // 3. MACD (12, 26, 9) Chart
        this.macdChart = LightweightCharts.createChart(macdEl, {
          ...baseOptions,
          width: macdEl.clientWidth || chartWidth,
          height: macdEl.clientHeight || 135,
        });
        const macdHist = this.macdChart.addHistogramSeries({ priceLineVisible: false });
        macdHist.setData(this.payload.macd?.histogram || []);
        const macdLine = this.macdChart.addLineSeries({ color: '#38bdf8', lineWidth: 1.5, priceLineVisible: false });
        macdLine.setData(this.payload.macd?.macd || []);
        const signalLine = this.macdChart.addLineSeries({ color: '#fb923c', lineWidth: 1.5, priceLineVisible: false });
        signalLine.setData(this.payload.macd?.signal || []);

        // Sync time scales across all 3 panes
        const charts = [this.mainChart, this.rsiChart, this.macdChart];
        let syncing = false;
        charts.forEach((src) => {
          src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
            if (syncing || !range) return;
            syncing = true;
            charts.forEach((dst) => {
              if (dst !== src) dst.timeScale().setVisibleLogicalRange(range);
            });
            syncing = false;
          });
        });

        // Hover readout on main chart
        this.mainChart.subscribeCrosshairMove((param) => {
          if (!param || !param.seriesData) return;
          const bar = param.seriesData.get(this.candleSeries);
          if (bar) {
            this.hoverInfo = `O:${this.formatNum(bar.open)} H:${this.formatNum(bar.high)} L:${this.formatNum(bar.low)} C:${this.formatNum(bar.close)}`;
          }
        });

        this.mainChart.timeScale().fitContent();

        // Responsive resize
        this.resizeHandler = () => {
          const w = mainEl.clientWidth || 800;
          if (this.mainChart) this.mainChart.applyOptions({ width: w });
          if (this.rsiChart) this.rsiChart.applyOptions({ width: rsiEl.clientWidth || w });
          if (this.macdChart) this.macdChart.applyOptions({ width: macdEl.clientWidth || w });
        };
        window.addEventListener('resize', this.resizeHandler);
      } catch (err) {
        console.error('Chart render error:', err);
        this.chartError = 'Gagal merender chart: ' + (err?.message || err);
      }
    },

    drawStrategyPriceLines() {
      if (!this.candleSeries || !this.levels) return;
      const lv = this.levels;

      if (lv.entry > 0) {
        this.candleSeries.createPriceLine({
          price: Number(lv.entry),
          color: '#38bdf8',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Solid,
          axisLabelVisible: true,
          title: 'ENTRY',
        });
      }
      if (lv.stop_loss > 0) {
        this.candleSeries.createPriceLine({
          price: Number(lv.stop_loss),
          color: '#f43f5e',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: `HARD SL (${lv.sl_pct}%)`,
        });
      }
      if (lv.target_1 > 0) {
        this.candleSeries.createPriceLine({
          price: Number(lv.target_1),
          color: '#10b981',
          lineWidth: 1.5,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: `TP1 (+${lv.tp1_pct}%)`,
        });
      }
      if (lv.target_2 && lv.target_2 > 0) {
        this.candleSeries.createPriceLine({
          price: Number(lv.target_2),
          color: '#34d399',
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dotted,
          axisLabelVisible: true,
          title: `TP2 (+${lv.tp2_pct}%)`,
        });
      }
      if (lv.trailing_active && lv.trailing_stop > 0) {
        this.trailingLineRef = this.candleSeries.createPriceLine({
          price: Number(lv.trailing_stop),
          color: '#fb923c',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.LargeDashed,
          axisLabelVisible: true,
          title: `TRAILING STOP (${lv.trailing_pullback_pct}%)`,
        });
      }
    },

    async fetchLiveQuote() {
      try {
        const res = await fetch(this.quoteUrl, { headers: { 'Accept': 'application/json' } });
        if (!res.ok) return;
        const q = await res.json();
        const last = Number(q.last ?? q.price ?? 0);
        if (last <= 0) return;

        this.livePrice = last;
        this.liveStatusText = q.is_live ? 'LIVE 15s' : 'SNAPSHOT';

        // Update latest candle live
        if (this.candleSeries && this.payload.candles && this.payload.candles.length > 0) {
          const lastCandle = { ...this.payload.candles[this.payload.candles.length - 1] };
          lastCandle.close = last;
          if (last > lastCandle.high) lastCandle.high = last;
          if (last < lastCandle.low) lastCandle.low = last;
          this.candleSeries.update(lastCandle);
        }

        // Dynamic Peak & Trailing Stop update when live price breaks new high
        if (last > Number(this.levels.peak_price || 0)) {
          this.levels.peak_price = last;
          const entry = Number(this.levels.entry || 0);
          const mfe = entry > 0 ? ((last - entry) / entry) * 100 : 0;
          this.levels.mfe_pct = Number(mfe.toFixed(2));
          if (last > entry && mfe >= Number(this.levels.trailing_activation_pct || 0)) {
            const newTs = Number((last * (1 - Number(this.levels.trailing_pullback_pct) / 100)).toFixed(2));
            this.levels.trailing_active = true;
            this.levels.trailing_stop = newTs;
            if (this.trailingLineRef) {
              this.candleSeries.removePriceLine(this.trailingLineRef);
            }
            this.trailingLineRef = this.candleSeries.createPriceLine({
              price: newTs,
              color: '#fb923c',
              lineWidth: 2,
              lineStyle: LightweightCharts.LineStyle.LargeDashed,
              axisLabelVisible: true,
              title: `TRAILING STOP (${this.levels.trailing_pullback_pct}%)`,
            });
          }
        }
      } catch (e) {
        this.liveStatusText = 'OFFLINE';
      }
    },
  };
}
</script>
</x-app-layout>

