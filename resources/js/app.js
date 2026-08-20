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
                    scales: {
                        x: { ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 8 }, grid: { display: false } },
                        y: {
                            ticks: {
                                color: '#64748b', font: { size: 10 },
                                callback: (v) => this.mode === 'rp'
                                    ? (Math.abs(v) >= 1000000 ? (v / 1000000).toFixed(1) + 'jt' : v.toLocaleString('id-ID'))
                                    : v + '%',
                            },
                            grid: { color: 'rgba(148,163,184,0.08)' },
                        },
                    },
                },
            });
            this.$watch('mode', () => this.updateChart());
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
                },
            ];
        },
        updateChart() {
            if (!this.chart) return;
            this.chart.data.datasets = this.buildDatasets();
            this.chart.options.plugins.legend.display = this.mode === 'ihsg';
            this.chart.options.scales.y.ticks.callback = (v) => this.mode === 'rp'
                ? (Math.abs(v) >= 1000000 ? (v / 1000000).toFixed(1) + 'jt' : v.toLocaleString('id-ID'))
                : v + '%';
            this.chart.update();
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
