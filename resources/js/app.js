import './bootstrap';

import Alpine from 'alpinejs';
import Chart from 'chart.js/auto';

window.Alpine = Alpine;
window.Chart = Chart;
window.universalSearchReady = () => Alpine.store('universalSearch')?.init();

// Dipakai priceQuote DAN tradePosition -- 20s pas jam bursa, lebih jarang di luar itu, supaya
// tidak spam request percuma pas market tutup.
function getQuotePollingInterval() {
    const now = new Date();
    const wib = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
    const hour = wib.getHours();
    const min = wib.getMinutes();
    const day = wib.getDay(); // 0=Sun, 6=Sat
    const timeNum = hour * 100 + min;

    if (day === 0 || day === 6) return 300000; // weekend
    if (timeNum >= 900 && timeNum <= 1130) return 20000; // sesi 1
    if (timeNum >= 1330 && timeNum <= 1500) return 20000; // sesi 2
    if (timeNum >= 845 && timeNum < 900) return 30000; // pre-market
    return 180000; // di luar jam
}

document.addEventListener('alpine:init', () => {
    // Kartu "Posisi Terbuka" di /trades -- harga & P&L update sendiri tanpa refresh halaman.
    // Reuse endpoint /api/stocks/{code}/quote yang sama dengan priceQuote di bawah, tapi
    // komponen terpisah karena butuh state tambahan (entryPrice/shares) untuk hitung P&L
    // reaktif -- priceQuote generik dipakai di banyak tempat lain, tidak diubah.
    Alpine.data('tradePosition', (entryPrice, shares, initialLast, initialIsLive, initialFetchedAt) => ({
        entryPrice,
        shares,
        last: initialLast ?? null,
        isLive: initialIsLive ?? false,
        fetchedAt: initialFetchedAt ?? null,
        pollingInterval: null,
        get hasPrice() {
            return this.last !== null && this.last > 0;
        },
        get pnl() {
            return this.hasPrice ? (this.last - this.entryPrice) * this.shares : null;
        },
        get pnlPercent() {
            return this.hasPrice ? (this.last - this.entryPrice) / this.entryPrice * 100 : null;
        },
        startPolling(url) {
            if (!url) return;
            const poll = () => {
                this.fetchQuote(url);
                this.pollingInterval = setTimeout(poll, getQuotePollingInterval());
            };
            this.pollingInterval = setTimeout(poll, getQuotePollingInterval());
        },
        async fetchQuote(url) {
            try {
                const res = await fetch(url);
                if (!res.ok) return;
                const data = await res.json();
                if (data && data.last) {
                    this.last = parseFloat(data.last);
                    this.isLive = data.is_live ?? this.isLive;
                    this.fetchedAt = data.fetched_at ?? this.fetchedAt;
                }
            } catch (e) {
                console.warn('Quote fetch error (tradePosition):', e);
            }
        },
        formatTime(iso) {
            if (!iso) return null;
            try {
                return new Date(iso).toLocaleTimeString('id-ID', {
                    hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta',
                }) + ' WIB';
            } catch (e) {
                return null;
            }
        },
    }));

    // Fase CU: chart Laporan Portofolio /trades/laporan -- toggle Rupiah kumulatif vs %-vs-IHSG,
    // dua-duanya sudah dikirim server sekaligus (portfolioRp/portfolioPct/ihsgPct sama-sama ada di
    // payload) supaya toggle-nya instan tanpa reload/request baru, cukup ganti dataset Chart.js.
    Alpine.data('portfolioChart', (data) => ({
        mode: 'rp',
        chart: null,
        init() {
            if (!data.labels || data.labels.length === 0) {
                return;
            }
            // Bug ditemukan user (toggle "vs IHSG" ganti state tombol tapi chart-nya diam tidak
            // ikut berubah): Chart.js dibuat SAAT Alpine masih jalan (init() sinkron di tengah
            // DOM walk), sebelum browser sempat selesai layout kontainer canvas -- Chart.js
            // ngukur ukuran yang belum settled, lalu update()/data-swap berikutnya tidak pernah
            // benar-benar redraw pixel-nya walau data internalnya sudah benar (dicek langsung:
            // chart.data.datasets sudah kepindah ke 2 dataset "Portofolio"/"IHSG", tapi canvas
            // TIDAK ikut ganti gambar). $nextTick nunda pembuatan chart sampai 1 tick setelah
            // DOM benar-benar settled.
            this.$nextTick(() => this.initChart());
            this.$watch('mode', () => this.updateChart());
        },
        initChart() {
            this.chart = new Chart(this.$refs.canvas, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: this.buildDatasets(),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: this.mode === 'ihsg',
                            labels: { color: '#94a3b8', font: { size: 11 } },
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const v = ctx.parsed.y;
                                    if (this.mode === 'rp') {
                                        return 'Rp' + Math.round(v).toLocaleString('id-ID');
                                    }
                                    return ctx.dataset.label + ': ' + (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
                                },
                            },
                        },
                    },
                    scales: this.buildScales(),
                },
            });
        },
        // Fase CW: sumbu Y dibagi jadi "y" (kiri, Portfolio) dan "yIhsg" (kanan, IHSG) di mode
        // vs IHSG -- angka Portfolio dan IHSG boleh punya rentang beda tanpa satu tenggelam.
        // Ganti scale set (y-only <-> y+yIhsg) lewat assignment `chart.options.scales = {...}`
        // ternyata bikin Chart.js v4 lempar "RangeError: Maximum call stack size exceeded" saat
        // update()/resize() -- resolver opsi internalnya rekursif kalau shape scales berubah di
        // tempat. Redraw jadi diam-diam gagal (data & scale kepindah di JS, canvas tidak pernah
        // ikut). Fix: destroy chart lalu initChart() ulang tiap ganti mode -- lebih mahal dikit
        // tapi selalu bikin instance Chart.js fresh, tidak pernah nyangkut di state lama.
        buildScales() {
            const xScale = { ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 8 }, grid: { display: false } };
            if (this.mode === 'rp') {
                return {
                    x: xScale,
                    y: {
                        ticks: {
                            color: '#64748b', font: { size: 10 },
                            callback: (v) => Math.abs(v) >= 1000000 ? (v / 1000000).toFixed(1) + 'jt' : v.toLocaleString('id-ID'),
                        },
                        grid: { color: 'rgba(148,163,184,0.08)' },
                    },
                };
            }
            return {
                x: xScale,
                y: {
                    position: 'left',
                    ticks: { color: '#4ade80', font: { size: 10 }, callback: (v) => v + '%' },
                    grid: { color: 'rgba(148,163,184,0.08)' },
                    title: { display: true, text: 'Portofolio', color: '#4ade80', font: { size: 10 } },
                },
                yIhsg: {
                    position: 'right',
                    ticks: { color: '#a78bfa', font: { size: 10 }, callback: (v) => v + '%' },
                    grid: { display: false },
                    title: { display: true, text: 'IHSG', color: '#a78bfa', font: { size: 10 } },
                },
            };
        },
        buildDatasets() {
            if (this.mode === 'rp') {
                return [{
                    label: 'Portofolio (Rp)',
                    data: data.portfolioRp,
                    borderColor: '#4ade80',
                    backgroundColor: 'rgba(74,222,128,0.1)',
                    fill: true,
                    tension: 0.15,
                    pointRadius: 0,
                    borderWidth: 2,
                }];
            }
            return [
                {
                    label: 'Portofolio',
                    data: data.portfolioPct,
                    borderColor: '#4ade80',
                    backgroundColor: 'transparent',
                    tension: 0.15,
                    pointRadius: 0,
                    borderWidth: 2,
                    yAxisID: 'y',
                },
                {
                    label: 'IHSG',
                    data: data.ihsgPct,
                    borderColor: '#a78bfa',
                    backgroundColor: 'transparent',
                    tension: 0.15,
                    pointRadius: 0,
                    borderWidth: 2,
                    borderDash: [4, 3],
                    yAxisID: 'yIhsg',
                },
            ];
        },
        updateChart() {
            if (!this.chart) return;
            this.chart.destroy();
            this.initChart();
        },
    }));

    // Fase CY: mini equity line chart (StockBit-style Total Equity card) + range filter
    // (1W/1M/3M/YTD/1Y/All). Data.portfolioRp SEKARANG = saldo akun (STARTING_CAPITAL + PnL kum)
    // langsung dari server, bukan reconstructed lagi. `range` state reactive -- ganti pilihan =
    // chart re-render dgn subset dates.
    Alpine.data('equityChart', (data) => ({
        chart: null,
        range: 'All',
        init() {
            if (!data.labels || data.labels.length === 0) return;
            this.$nextTick(() => this.initChart());
            this.$watch('range', () => this.updateChart());
        },
        // Fase CY: pilih rentang berdasar `data.dates` (ISO YYYY-MM-DD dari server, tidak ambigu
        // antar tahun spt 'd M'). Kembalikan indeks awal (start) dari array full utk di-slice.
        rangeStartIndex() {
            const dates = data.dates || [];
            if (dates.length === 0 || this.range === 'All') return 0;
            const lastDate = new Date(dates[dates.length - 1] + 'T00:00:00');
            let cutoff = new Date(lastDate);
            switch (this.range) {
                case '1W': cutoff.setDate(lastDate.getDate() - 7); break;
                case '1M': cutoff.setMonth(lastDate.getMonth() - 1); break;
                case '3M': cutoff.setMonth(lastDate.getMonth() - 3); break;
                case 'YTD': cutoff = new Date(lastDate.getFullYear(), 0, 1); break;
                case '1Y': cutoff.setFullYear(lastDate.getFullYear() - 1); break;
                default: return 0;
            }
            const cutoffIso = cutoff.toISOString().slice(0, 10);
            for (let i = 0; i < dates.length; i++) {
                if (dates[i] >= cutoffIso) return i;
            }
            return dates.length - 1;
        },
        sliced() {
            const start = this.rangeStartIndex();
            return {
                labels: data.labels.slice(start),
                equity: data.portfolioRp.slice(start),
            };
        },
        initChart() {
            const s = this.sliced();
            this.chart = new Chart(this.$refs.canvas, {
                type: 'line',
                data: {
                    labels: s.labels,
                    datasets: [{
                        data: s.equity,
                        borderColor: '#4ade80',
                        backgroundColor: 'rgba(74,222,128,0.12)',
                        fill: true,
                        tension: 0.15,
                        pointRadius: 0,
                        borderWidth: 1.5,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => 'Rp' + Math.round(ctx.parsed.y).toLocaleString('id-ID'),
                            },
                        },
                    },
                    scales: {
                        x: { display: false },
                        y: { display: false },
                    },
                },
            });
        },
        // Fase CY: destroy+recreate tiap ganti range -- pola yang sama dgn portfolioChart (Fase CW).
        // `chart.update()` doang kadang tidak repaint canvas walau data internal sudah benar
        // (bug Chart.js v4 di kombinasi container kecil + data range yg beda drastis). Destroy
        // paksa Chart.js bikin instance baru dari nol, canvas dijamin fresh.
        updateChart() {
            if (!this.chart) return;
            this.chart.destroy();
            this.initChart();
        },
    }));

    // Fase CX: Portfolio Allocation donut (open positions). Data = [{ticker, positions, value, pct}].
    // Warna cycling supaya tiap saham beda warna tanpa perlu palette per-saham eksplisit.
    Alpine.data('allocationDonut', (allocations) => ({
        chart: null,
        init() {
            if (!allocations || allocations.length === 0) return;
            this.$nextTick(() => this.initChart());
        },
        initChart() {
            const palette = ['#4ade80', '#a78bfa', '#38bdf8', '#f472b6', '#fbbf24', '#f87171', '#22d3ee', '#fb923c'];
            this.chart = new Chart(this.$refs.canvas, {
                type: 'doughnut',
                data: {
                    labels: allocations.map(a => a.ticker),
                    datasets: [{
                        data: allocations.map(a => a.value),
                        backgroundColor: allocations.map((_, i) => palette[i % palette.length]),
                        borderColor: '#0f172a',
                        borderWidth: 2,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    cutout: '68%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const a = allocations[ctx.dataIndex];
                                    return a.ticker + ': Rp' + a.value.toLocaleString('id-ID') + ' (' + a.pct + '%)';
                                },
                            },
                        },
                    },
                },
            });
        },
    }));

    Alpine.data('priceQuote', (initialQuote, fallbackChange) => ({
        quote: {
            stock_code: initialQuote?.stock_code ?? null,
            last: initialQuote?.last ?? null,
            open: initialQuote?.open ?? null,
            high: initialQuote?.high ?? null,
            low: initialQuote?.low ?? null,
            close: initialQuote?.close ?? null,
            volume: initialQuote?.volume ?? null,
            change_percent: initialQuote?.change_percent ?? fallbackChange ?? null,
            source: initialQuote?.source ?? null,
            is_live: initialQuote?.is_live ?? false,
            fetched_at: initialQuote?.fetched_at ?? null,
        },
        pollingInterval: null,
        startPolling(url) {
            if (!url) return;
            this.fetchQuote(url);
            const poll = () => {
                this.fetchQuote(url);
                this.pollingInterval = setTimeout(poll, getQuotePollingInterval());
            };
            this.pollingInterval = setTimeout(poll, getQuotePollingInterval());
        },
        async fetchQuote(url) {
            try {
                const res = await fetch(url);
                if (!res.ok) return;
                const data = await res.json();
                if (data && ((data.last ?? 0) > 0 || (data.open ?? 0) > 0)) {
                    this.quote = {
                        ...this.quote,
                        ...data,
                        open: data.open ? parseFloat(data.open) : this.quote.open,
                        high: data.high ? parseFloat(data.high) : this.quote.high,
                        low: data.low ? parseFloat(data.low) : this.quote.low,
                        close: data.close ? parseFloat(data.close) : this.quote.close,
                        last: data.last ? parseFloat(data.last) : this.quote.last,
                        volume: data.volume ? parseInt(data.volume) : this.quote.volume,
                    };
                }
            } catch (e) {
                console.warn('Quote fetch error:', e);
            }
        },
        formatNumber(val) {
            const n = parseFloat(val);
            if (Number.isNaN(n) || val === null || val === undefined) return '—';
            return n.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },
        formatVolume(val) {
            const n = parseFloat(val);
            if (Number.isNaN(n) || val === null || val === undefined) return '—';
            if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + 'B';
            if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
            if (n >= 1_000) return (n / 1_000).toFixed(2) + 'K';
            return n.toLocaleString('id-ID');
        },
        formatPercent(val) {
            const n = parseFloat(val);
            if (Number.isNaN(n) || val === null || val === undefined) return '—';
            const sign = n >= 0 ? '+' : '';
            return sign + n.toFixed(2) + '%';
        },
        changePercent() {
            return parseFloat(this.quote?.change_percent) || 0;
        },
        marketStatus() {
            const now = new Date();
            const wib = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
            const hour = wib.getHours();
            const min = wib.getMinutes();
            const day = wib.getDay();
            const timeNum = hour * 100 + min;

            if (day === 0 || day === 6) return { label: 'Market Tutup', color: 'text-slate-400', dot: 'bg-slate-400' };
            if (timeNum >= 900 && timeNum <= 1130) return { label: 'Sesi 1', color: 'text-green-400', dot: 'bg-green-400' };
            if (timeNum >= 1130 && timeNum < 1330) return { label: 'Istirahat', color: 'text-yellow-400', dot: 'bg-yellow-400' };
            if (timeNum >= 1330 && timeNum <= 1500) return { label: 'Sesi 2', color: 'text-green-400', dot: 'bg-green-400' };
            if (timeNum >= 845 && timeNum < 900) return { label: 'Pre-Market', color: 'text-sky-400', dot: 'bg-sky-400' };
            if (timeNum > 1500 && timeNum <= 1515) return { label: 'Post-Trading', color: 'text-orange-400', dot: 'bg-orange-400' };
            return { label: 'After Hours', color: 'text-slate-400', dot: 'bg-slate-400' };
        },
    }));
});

document.addEventListener('alpine:init', () => {
    Alpine.store('universalSearch', {
        query: '',
        isOpen: false,
        isLoading: false,
        error: null,
        selectedIndex: -1,
        activeFilters: ['stocks', 'news', 'pages', 'actions'],
        results: { stocks: [], news: [], pages: [], actions: [] },
        history: [],
        filters: [
            { key: 'stocks', label: 'Saham' },
            { key: 'news', label: 'Berita' },
            { key: 'pages', label: 'Halaman' },
            { key: 'actions', label: 'Aksi Cepat' },
        ],
        sections: [
            { key: 'stocks', label: 'Saham' },
            { key: 'actions', label: 'Aksi Cepat' },
            { key: 'news', label: 'Berita' },
            { key: 'pages', label: 'Halaman' },
        ],
        defaultActions: [
            { type: 'action', label: 'Aksi Cepat', title: 'Watchlist Saya', subtitle: 'Buka daftar saham favorit', meta: 'Aksi', url: '/watchlist' },
            { type: 'action', label: 'Aksi Cepat', title: 'Prediksi Saham', subtitle: 'Buka analisis prediksi saham', meta: 'Aksi', url: '/analytics' },
            { type: 'action', label: 'Aksi Cepat', title: 'Berita Terkini', subtitle: 'Buka feed berita pasar', meta: 'Aksi', url: '/news' },
            { type: 'action', label: 'Aksi Cepat', title: 'Evaluasi Model', subtitle: 'Buka laporan evaluasi model', meta: 'Aksi', url: '/evaluasi' },
            { type: 'action', label: 'Aksi Cepat', title: 'Backtest DSS', subtitle: 'Buka simulasi historis DSS', meta: 'Aksi', url: '/backtest' },
        ],
        quickChips: [
            { label: 'BBCA', query: 'BBCA' },
            { label: 'TLKM', query: 'TLKM' },
            { label: 'Evaluasi', query: 'evaluasi' },
            { label: 'Backtest', query: 'backtest' },
        ],
        init() {
            this.loadHistory();
            window.addEventListener('keydown', (event) => {
                if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                    event.preventDefault();
                    this.focusInput();
                }
            });
        },
        open() {
            this.isOpen = true;
        },
        close() {
            this.isOpen = false;
            this.selectedIndex = -1;
        },
        focusInput() {
            this.open();
            requestAnimationFrame(() => document.querySelector('[data-universal-search-input]')?.focus());
        },
        clear() {
            this.query = '';
            this.results = { stocks: [], news: [], pages: [], actions: [] };
            this.error = null;
            this.selectedIndex = -1;
            this.open();
            this.focusInput();
        },
        useQuickChip(item) {
            this.query = item.query;
            this.open();
            this.focusInput();
            this.search();
        },
        resetFilters() {
            this.activeFilters = ['stocks', 'news', 'pages', 'actions'];
            this.search();
        },
        toggleFilter(key) {
            if (this.activeFilters.includes(key)) {
                if (this.activeFilters.length === 1) return;
                this.activeFilters = this.activeFilters.filter((item) => item !== key);
            } else {
                this.activeFilters.push(key);
            }
            this.search();
        },
        async search() {
            this.open();
            this.error = null;
            this.selectedIndex = -1;

            if (this.query.trim().length < 2) {
                this.results = { stocks: [], news: [], pages: [], actions: [] };
                this.isLoading = false;
                return;
            }

            this.isLoading = true;
            try {
                const { data } = await window.axios.get('/universal-search', {
                    params: {
                        q: this.query.trim(),
                        types: this.activeFilters,
                    },
                });
                this.results = data.results ?? { stocks: [], news: [], pages: [], actions: [] };
            } catch (error) {
                console.error(error);
                this.error = error;
            } finally {
                this.isLoading = false;
            }
        },
        flatResults() {
            return this.sections.flatMap((section) => this.results[section.key] ?? []);
        },
        hasResults() {
            return this.flatResults().length > 0;
        },
        move(direction) {
            this.open();
            const items = this.flatResults();
            if (!items.length) return;
            this.selectedIndex = (this.selectedIndex + direction + items.length) % items.length;
        },
        isSelected(item) {
            return this.flatResults()[this.selectedIndex] === item;
        },
        openSelected() {
            const item = this.flatResults()[this.selectedIndex];
            if (item) this.openItem(item);
        },
        openItem(item) {
            this.saveHistory(item);
            window.location.href = item.url;
        },
        loadHistory() {
            try {
                this.history = JSON.parse(localStorage.getItem('universal_search_history') || '[]');
            } catch {
                this.history = [];
            }
        },
        saveHistory(item) {
            const normalized = {
                type: item.type,
                label: item.label,
                title: item.title,
                subtitle: item.subtitle,
                meta: item.meta,
                url: item.url,
            };
            this.history = [normalized, ...this.history.filter((entry) => entry.url !== normalized.url)].slice(0, 5);
            localStorage.setItem('universal_search_history', JSON.stringify(this.history));
        },
        clearHistory() {
            this.history = [];
            localStorage.removeItem('universal_search_history');
        },
        iconFor(type) {
            return { stock: 'IDX', news: '📰', page: '↗', action: '⌘' }[type] ?? '⌕';
        },
        iconClass(type) {
            return {
                stock: 'universal-search-icon-stock',
                news: 'universal-search-icon-news',
                page: 'universal-search-icon-page',
                action: 'universal-search-icon-action',
            }[type] ?? '';
        },
        escapeHtml(value) {
            return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#039;',
                '"': '&quot;',
            })[char]);
        },
        highlightMatch(text) {
            const safeText = this.escapeHtml(text);
            const needle = this.query.trim();
            if (!needle) return safeText;
            const safeNeedle = this.escapeHtml(needle).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            return safeText.replace(new RegExp(`(${safeNeedle})`, 'ig'), '<mark class="universal-search-mark">$1</mark>');
        },
    });

    Alpine.store('stockSearch', {
        query: '',
        results: [],
        loading: false,
        async search() {
            if (this.query.length < 2) {
                this.results = [];
                return;
            }

            this.loading = true;
            try {
                const { data } = await window.axios.get('/stocks/search', {
                    params: { q: this.query },
                });
                this.results = data;
            } catch (error) {
                console.error(error);
            } finally {
                this.loading = false;
            }
        },
    });

    Alpine.data('stockTicker', (stockCode, initialPrice, initialChange) => ({
        price: parseFloat(initialPrice) || null,
        changePercent: parseFloat(initialChange) || null,
        isLive: false,
        pollingInterval: null,
        init() {
            const delay = Math.random() * 3000;
            setTimeout(() => {
                this.fetchPrice();
                this.pollingInterval = setInterval(() => this.fetchPrice(), 30000);
            }, delay);
        },
        async fetchPrice() {
            try {
                const res = await fetch(`/api/stocks/${stockCode}/quote`);
                if (!res.ok) return;
                const data = await res.json();
                if (data && (data.last ?? 0) > 0) {
                    this.price = data.last ? parseFloat(data.last) : this.price;
                    this.changePercent = data.change_percent !== undefined && data.change_percent !== null
                        ? parseFloat(data.change_percent)
                        : this.changePercent;
                    this.isLive = data.is_live ?? false;
                }
            } catch (e) {
                // keep existing price on error
            }
        },
        formatPrice(val) {
            const n = parseFloat(val);
            if (Number.isNaN(n) || val === null || val === undefined) return '—';
            return n.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },
        formatPercent(val) {
            const n = parseFloat(val);
            if (Number.isNaN(n) || val === null || val === undefined) return '—';
            return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
        },
    }));

    Alpine.data('dashboardPage', () => ({
        rightPanelOpen: true,
        init() {
            const saved = localStorage.getItem('sentimena_rightpanel_open');
            this.rightPanelOpen = saved === null ? true : saved === 'true';
        },
        toggleRightPanel(forceState = null) {
            this.rightPanelOpen = typeof forceState === 'boolean'
                ? forceState
                : !this.rightPanelOpen;
            localStorage.setItem('sentimena_rightpanel_open', String(this.rightPanelOpen));
        },
    }));

});

Alpine.start();
