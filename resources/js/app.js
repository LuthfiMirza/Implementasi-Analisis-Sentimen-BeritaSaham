import './bootstrap';

import Alpine from 'alpinejs';
import Chart from 'chart.js/auto';

window.Alpine = Alpine;
window.Chart = Chart;

document.addEventListener('alpine:init', () => {
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
            const getInterval = () => {
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
            };

            this.fetchQuote(url);
            const poll = () => {
                this.fetchQuote(url);
                this.pollingInterval = setTimeout(poll, getInterval());
            };
            this.pollingInterval = setTimeout(poll, getInterval());
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
});

Alpine.start();
