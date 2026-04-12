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
            this.fetchQuote(url);
            this.pollingInterval = setInterval(() => this.fetchQuote(url), 20000);
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
