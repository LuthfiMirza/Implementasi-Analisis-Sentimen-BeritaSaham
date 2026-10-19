<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>Stockbit Portfolio | Stockbit - Investasi Saham Bersama Komunitas Saham Terbesar di Indonesia</title>

    <!-- Chart.js & Alpine.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js"></script>

    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        [x-cloak] {
            display: none !important;
        }
        html {
            scroll-behavior: smooth;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #F8F9FA;
            color: #333333;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* ── Stockbit Header Bar ── */
        .sb-header-web {
            background: #FFFFFF;
            border-bottom: 1px solid #EBECEF;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .sb-top-navbar {
            max-width: 1400px;
            margin: 0 auto;
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
        }
        .sb-logo-search {
            display: flex;
            align-items: center;
            gap: 24px;
            flex: 1;
            max-width: 580px;
        }
        .sb-logo-svg {
            display: flex;
            align-items: center;
            text-decoration: none;
            color: #00AA5B;
            font-weight: 800;
            font-size: 20px;
            letter-spacing: -0.5px;
        }
        .sb-search-wrapper {
            position: relative;
            width: 100%;
            max-width: 340px;
        }
        .sb-search-input {
            width: 100%;
            height: 32px;
            padding: 0 12px 0 32px;
            background: #F4F5F7;
            border: 1px solid transparent;
            border-radius: 6px;
            font-size: 12px;
            color: #333333;
            outline: none;
            transition: all 0.2s ease;
        }
        .sb-search-input:focus {
            background: #FFFFFF;
            border-color: #00AA5B;
        }
        .sb-search-icon {
            position: absolute;
            left: 10px;
            top: 8px;
            color: #98A2B3;
            pointer-events: none;
        }
        .sb-top-actions {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .sb-icon-badge-btn {
            position: relative;
            background: transparent;
            border: none;
            cursor: pointer;
            color: #969696;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 4px;
        }
        .sb-badge-count {
            position: absolute;
            top: -2px;
            right: -6px;
            background: #EE4A49;
            color: #FFFFFF;
            font-size: 10px;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 10px;
            line-height: 1;
        }
        .sb-user-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            overflow: hidden;
            background: #E5E7EB;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 12px;
            color: #333333;
        }
        .sb-dashboard-return-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 600;
            color: #00AA5B;
            background: #E8F8F1;
            padding: 5px 12px;
            border-radius: 6px;
            text-decoration: none;
            transition: all 0.15s ease;
        }
        .sb-dashboard-return-btn:hover {
            background: #D1F2E3;
        }

        /* ── Sub Navigation Menu (Stream, Profile, Portfolio, etc.) ── */
        .sb-sub-navbar {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            overflow-x: auto;
            scrollbar-width: none;
        }
        .sb-sub-navbar::-webkit-scrollbar {
            display: none;
        }
        .sb-sub-nav-links {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .sb-sub-nav-item {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 10px 12px;
            font-size: 13px;
            color: #667085;
            text-decoration: none;
            white-space: nowrap;
            border-bottom: 2px solid transparent;
            font-weight: 500;
            transition: all 0.15s ease;
        }
        .sb-sub-nav-item:hover {
            color: #111111;
        }
        .sb-sub-nav-item.active {
            color: #00AA5B;
            font-weight: 700;
            border-bottom-color: #00AA5B;
        }
        .sb-sub-nav-item svg {
            width: 15px;
            height: 15px;
        }
        .sb-trading-area-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: #FFFFFF;
            border: 1px solid #D0D5DD;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            color: #333333;
            cursor: pointer;
            white-space: nowrap;
        }

        /* ── Main Layout Container ── */
        .sb-main-layout {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 24px 60px;
        }

        /* Ant-Design Radio Buttons [Portfolio | Order | History] */
        .sb-radio-group {
            display: inline-flex;
            border-radius: 4px;
            background: #FFFFFF;
            border: 1px solid #D9D9D9;
            overflow: hidden;
            margin-bottom: 16px;
        }
        .sb-radio-btn {
            border: none;
            background: #FFFFFF;
            color: #333333;
            font-size: 13px;
            font-weight: 500;
            padding: 6px 18px;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-right: 1px solid #D9D9D9;
            transition: all 0.2s ease;
        }
        .sb-radio-btn:last-child {
            border-right: none;
        }
        .sb-radio-btn.active {
            color: #00AA5B;
            font-weight: 700;
            box-shadow: inset 0 0 0 1px #00AA5B;
        }
        .sb-radio-btn:disabled {
            color: #B5B5B5;
            cursor: not-allowed;
        }

        /* ── 5-Metric Header Strip ala Stockbit (bXOKmr) ── */
        .sb-metrics-strip {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #FFFFFF;
            border: 1px solid #EBECEF;
            border-radius: 8px;
            padding: 16px 28px;
            margin-bottom: 16px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        }
        .sb-metric-col {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .sb-metric-num {
            font-size: 20px;
            font-weight: 700;
            color: #333333;
            line-height: 1.35;
            letter-spacing: -0.2px;
        }
        .sb-metric-lbl {
            font-size: 12px;
            font-weight: 400;
            color: #B5B5B5;
            line-height: 1.35;
        }

        /* ── Main Outer White Card (kukLdZ) ── */
        .sb-main-card {
            background: #FFFFFF;
            border: 1px solid #EBECEF;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
            margin-bottom: 24px;
        }

        /* Subheader Bar (Stocks 0%, Bonds 0%, Performance) */
        .sb-card-subheader {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 20px;
            border-bottom: 1px solid #EBECEF;
            background: #FFFFFF;
        }
        .sb-filter-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .sb-filter-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: transparent;
            border: none;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            color: #4F5E71;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .sb-filter-btn:hover {
            background: #F4F5F7;
        }
        .sb-filter-badge {
            background: #F2F4F7;
            color: #475467;
            font-size: 11px;
            font-weight: 600;
            padding: 1px 5px;
            border-radius: 4px;
        }
        .sb-perf-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #FFFFFF;
            border: 1px solid #8228BD;
            border-radius: 5px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 600;
            color: #8228BD;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .sb-perf-btn:hover {
            background: #F9F5FF;
        }

        /* ── Card Body (dlgtTy) ── */
        .sb-card-body {
            padding: 20px;
        }

        /* ── 3-Column Performance Grid ── */
        .sb-performance-grid {
            display: grid;
            grid-template-columns: 44% 31% 25%;
            gap: 16px;
            align-items: stretch;
        }

        /* Individual Boxes */
        .sb-box {
            background: #FFFFFF;
            border: 1px solid #EBECEF;
            border-radius: 8px;
            padding: 16px 20px;
            position: relative;
        }
        .sb-box-title {
            font-size: 14px;
            font-weight: 700;
            color: #333333;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .sb-box-num {
            font-size: 20px;
            font-weight: 700;
            color: #111111;
            margin-top: 4px;
            margin-bottom: 8px;
            letter-spacing: -0.3px;
        }

        /* Legend box for Cumulative Return */
        .sb-legend-split-box {
            background: #FFFFFF;
            border: 1px solid #EBECEF;
            border-radius: 6px;
            padding: 6px 14px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .sb-legend-half {
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 46%;
        }
        .sb-legend-divider {
            width: 1px;
            height: 18px;
            background: #EBECEF;
        }

        /* Range selector (1W, 1M, 3M, YTD, 1Y, All) */
        .sb-range-selector {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            margin-top: 10px;
        }
        .sb-range-opt {
            background: none;
            border: none;
            font-size: 11px;
            font-weight: 600;
            color: #969696;
            padding: 4px 2px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.15s ease;
        }
        .sb-range-opt:hover {
            color: #333333;
        }
        .sb-range-opt.active {
            color: #00AB6B;
            font-weight: 700;
            border-bottom-color: #00AB6B;
        }

        /* Dropdown pills & Toggle pills */
        .sb-toggle-pills {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 10px;
            margin-bottom: 12px;
        }
        .sb-pill-active {
            border: 1px solid #00AB6B;
            color: #00AB6B;
            font-weight: 600;
            font-size: 11px;
            padding: 2px 12px;
            border-radius: 14px;
            background: #FFFFFF;
            cursor: pointer;
        }
        .sb-pill-inactive {
            border: none;
            color: #969696;
            font-size: 11px;
            font-weight: 500;
            padding: 2px 12px;
            background: transparent;
            cursor: pointer;
        }
        .sb-pill-inactive:hover {
            color: #333333;
        }
        .sb-dropdown-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 1px solid #D0D5DD;
            border-radius: 16px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 500;
            color: #344054;
            background: #FFFFFF;
            cursor: pointer;
        }

        /* Tables (Date, Equity, P&L) */
        .sb-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .sb-table th {
            padding: 6px 0 10px;
            font-size: 11px;
            font-weight: 600;
            color: #969696;
            border-bottom: 1px solid #F0F2F5;
            background: #FFFFFF;
            white-space: nowrap;
        }
        .sb-table td {
            padding: 9px 0;
            border-bottom: 1px solid #F9FAFB;
            color: #333333;
            font-size: 12px;
            font-weight: 500;
            vertical-align: middle;
            white-space: nowrap;
        }
        .sb-table tr:last-child td {
            border-bottom: none;
        }
        .sb-scroll-area {
            max-height: 440px;
            overflow-y: auto;
            padding-right: 4px;
            scrollbar-width: thin;
            scrollbar-color: #E5E7EB transparent;
        }
        .sb-scroll-area::-webkit-scrollbar {
            width: 4px;
        }
        .sb-scroll-area::-webkit-scrollbar-thumb {
            background: #E5E7EB;
            border-radius: 4px;
        }

        /* ── Divider between Performance and Trade Summary ── */
        .sb-section-divider {
            height: 1px;
            background: #EBECEF;
            margin: 28px -20px 24px -20px;
        }

        /* ── Trade Summary Header & 2-Col Grid ── */
        .sb-trade-summary-hdr {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }
        .sb-trade-summary-title {
            font-size: 15px;
            font-weight: 700;
            color: #111111;
        }
        .sb-history-grid {
            display: grid;
            grid-template-columns: 46% 54%;
            gap: 16px;
            align-items: start;
        }

        /* Colors exact Stockbit */
        .c-green { color: #00AB6B !important; }
        .c-red { color: #EE4A49 !important; }
        .c-purple { color: #8228BD !important; }
        .c-gray { color: #969696 !important; }

        @media (max-width: 1024px) {
            .sb-performance-grid { grid-template-columns: 1fr; }
            .sb-history-grid { grid-template-columns: 1fr; }
            .sb-metrics-strip { flex-wrap: wrap; gap: 16px; }
        }
    </style>
</head>
<body x-data="stockbitPortfolioApp({
    chart: @js($portfolioReport['chart']),
    allocation: @js($portfolioReport['allocation']),
    realizedCurve: @js($realizedCurve),
    startingCapital: 10000000,
    currentEquity: {{ $totalEquity }},
    winRate: {{ $stats['win_rate'] }},
    winCount: {{ $stats['win'] }},
    lossCount: {{ $stats['loss'] }},
    totalTrades: {{ $stats['closed'] }}
})">

    <!-- ═════════════════════════════════════════════════════════ -->
    <!-- STOCKBIT HEADER WEB                                       -->
    <!-- ═════════════════════════════════════════════════════════ -->
    <header class="sb-header-web">
        <!-- Top row: logo, search, inbox, notification, profile, return to dashboard -->
        <div class="sb-top-navbar">
            <div class="sb-logo-search">
                <a href="{{ route('trades.portfolio') }}" class="sb-logo-svg">
                    <!-- Stockbit Logo Icon & Text -->
                    <svg width="28" height="28" viewBox="0 0 40 40" fill="none" style="margin-right:8px;">
                        <rect width="40" height="40" rx="8" fill="#00AA5B"/>
                        <path d="M12 28L18 16L24 24L28 14" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span style="color:#111111; font-weight:800; font-size:18px;">stockbit</span>
                </a>

                <!-- Search Input -->
                <div class="sb-search-wrapper">
                    <span class="sb-search-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    </span>
                    <input type="text" class="sb-search-input" placeholder="Search for brand, symbol or username...">
                </div>
            </div>

            <div class="sb-top-actions">
                <!-- Return link to Sentimena main dashboard -->
                <a href="{{ route('trades.index') }}" class="sb-dashboard-return-btn">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                    <span>Dashboard Sentimena</span>
                </a>

                <!-- Chat / Inbox -->
                <button class="sb-icon-badge-btn" title="Inbox">
                    <svg width="22" height="22" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M25 9V19C25 20.1 24.1 21 23 21H9L5 25V9C5 7.9 5.9 7 7 7H23C24.1 7 25 7.9 25 9Z" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    <span class="sb-badge-count">97</span>
                </button>

                <!-- Notifications -->
                <button class="sb-icon-badge-btn" title="Notifications">
                    <svg width="22" height="22" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17.5625 23.8767C17.009 24.707 16.066 25.2502 15 25.2502C13.934 25.2502 12.991 24.707 12.4375 23.8767" stroke-linecap="round" stroke-linejoin="round"/><path d="M25.25 21.15H4.75C4.75 21.15 7.825 17.5625 7.825 11.925C7.825 7.95825 11.0332 4.75 15 4.75C16.9885 4.75 18.772 5.5495 20.0738 6.85125C21.3755 8.14275 22.175 9.94675 22.175 11.925C22.175 17.5625 25.25 21.15 25.25 21.15Z" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    <span class="sb-badge-count">99+</span>
                </button>

                <!-- User profile avatar -->
                <div class="sb-user-avatar" title="{{ auth()->user()->name ?? 'Trader' }}">
                    {{ strtoupper(substr(auth()->user()->name ?? 'T', 0, 1)) }}
                </div>
            </div>
        </div>

        <!-- Secondary Sub Navigation Bar (Stream, Profile, Watchlist, Portfolio, etc.) -->
        <div class="sb-sub-navbar">
            <div class="sb-sub-nav-links">
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M12.68 2.37H3.31C2.79 2.37 2.37 2.79 2.37 3.31V12.68C2.37 13.2 2.79 13.62 3.31 13.62H12.68C13.2 13.62 13.62 13.2 13.62 12.68V3.31C13.62 2.79 13.2 2.37 12.68 2.37Z" stroke-width="1.2"/><path d="M5.74 6.28H10.24M5.74 9.68H10.24" stroke-width="1.2"/></svg>
                    <span>Stream</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><circle cx="8" cy="5.3" r="2.8" stroke-width="1.25"/><path d="M13.26 13.5C13.26 10.6 10.9 8.24 8 8.24C5.1 8.24 2.74 10.6 2.74 13.5H13.26Z" stroke-width="1.25"/></svg>
                    <span>Profile</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M8.3 1.4L10.14 5.15L14.27 5.75L11.47 9.23L12.18 13.34L8 11.75L3.82 13.34L4.53 9.23L1.54 5.75L5.86 5.15L8.3 1.4Z" stroke-width="1.2"/></svg>
                    <span>Watchlist</span>
                </a>
                <a href="{{ route('trades.portfolio') }}" class="sb-sub-nav-item active">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M13.56 9.75C12.82 12.12 10.61 13.83 8 13.83C4.78 13.83 2.17 11.22 2.17 8C2.17 5.39 3.88 3.18 6.25 2.44" stroke-width="1.2"/><path d="M13.83 8H8V2.17C11.23 2.17 13.83 4.78 13.83 8Z" stroke-width="1.2"/></svg>
                    <span>Portfolio</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><rect x="2.6" y="1.3" width="10.7" height="13.3" rx="1" stroke-width="1.2"/><path d="M2.6 4H13.3M5.3 8H6M8 8H10.7M5.3 10.7H6M8 10.7H10.7" stroke-width="1.2"/></svg>
                    <span>Orderbook</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><rect x="9.3" y="4" width="4" height="8" rx="1" stroke-width="1.2"/><rect x="2.6" y="4.6" width="4" height="6.6" rx="1" stroke-width="1.2"/><path d="M11.3 1.3V4M11.3 12V14.6M4.6 2.3V4.6M4.6 11.3V13.6" stroke-width="1.2"/></svg>
                    <span>Chartbit</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M1.4 1.4H14.6L13.8 11.8L8 14.6L2.1 11.8L1.4 1.4Z" stroke-width="1.2"/><path d="M4.5 4.9V8.5M6.4 4.9V8.5M8 4.9H6.4V6.7H8V4.9Z" stroke-width="1.2"/></svg>
                    <span>e-IPO</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M9.66 10V13.33H6.33V10L2.35 5.67C2.12 5.42 2 5.1 2 4.77V2.67H13.33V4.81C13.33 5.15 13.2 5.47 12.97 5.72L9.66 10Z" stroke-width="1.2"/><path d="M9.66 4.66H6.33" stroke-width="1.2"/></svg>
                    <span>Screener</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><ellipse cx="8" cy="7.7" rx="6.1" ry="2" stroke-width="1.2"/><path d="M5 6.7L5.7 3C5.7 2.6 6.1 2.3 6.5 2.3C7.5 2.8 8.6 2.8 9.5 2.3C9.9 2.3 10.3 2.6 10.3 3L11 6.7" stroke-width="1.2"/><path d="M4 9.3L4.8 11.2C5.2 12.2 6 13 7 13.4L8 13.7L9 13.4C10 13 10.8 12.2 11.2 11.2L12 9.3" stroke-width="1.2"/></svg>
                    <span>Broker Analysis</span>
                </a>
                <a href="#" class="sb-sub-nav-item">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M15.3 6L8 9.9L0.6 6L8 2L15.3 6Z" stroke-width="1.2"/><path d="M12.5 7.5V11.3C12.5 12.6 10.5 13.9 8 13.9C5.5 13.9 3.5 12.6 3.5 11.3V7.5" stroke-width="1.2"/></svg>
                    <span>Academy</span>
                </a>
            </div>

            <div class="sb-trading-area-btn">
                <span style="display:flex; align-items:center; gap:6px;">
                    <span style="width:16px; height:16px; background:#00AA5B; border-radius:3px; display:inline-flex; align-items:center; justify-content:center; color:#FFF; font-weight:800; font-size:9px;">SSD</span>
                    <span>Trading Area</span>
                </span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#667085" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
            </div>
        </div>
    </header>

    <!-- ═════════════════════════════════════════════════════════ -->
    <!-- MAIN CONTENT CONTAINER                                    -->
    <!-- ═════════════════════════════════════════════════════════ -->
    <main class="sb-main-layout">

        <!-- 1. Ant-Design Radio Buttons [Portfolio | Order | History] -->
        <div class="sb-radio-group">
            <a href="#portfolio-section" class="sb-radio-btn active">Portfolio</a>
            <button type="button" class="sb-radio-btn" disabled>Order</button>
            <a href="#history-section" class="sb-radio-btn">History</a>
        </div>

        <!-- 2. 5-Metric Header Strip ala Stockbit (bXOKmr) -->
        <div class="sb-metrics-strip">
            <!-- 1. Trading Balance -->
            <div class="sb-metric-col" style="text-align:left;">
                <div class="sb-metric-num">{{ number_format($tradingBalance, 0, '.', ',') }}</div>
                <div class="sb-metric-lbl">Trading Balance</div>
            </div>
            <!-- 2. Invested -->
            <div class="sb-metric-col" style="text-align:center;">
                <div class="sb-metric-num">{{ number_format($invested, 0, '.', ',') }}</div>
                <div class="sb-metric-lbl">Invested</div>
            </div>
            <!-- 3. Open -->
            <div class="sb-metric-col" style="text-align:center;">
                <div class="sb-metric-num">{{ $openCount }}</div>
                <div class="sb-metric-lbl">Open</div>
            </div>
            <!-- 4. Net Profit / Loss -->
            <div class="sb-metric-col" style="text-align:center;">
                <div class="sb-metric-num {{ $netFloatingPnl > 0 ? 'c-green' : ($netFloatingPnl < 0 ? 'c-red' : '') }}">
                    {{ number_format($netFloatingPnl, 0, '.', ',') }} ({{ ($netFloatingPnl >= 0 ? '+' : '').$netFloatingPnlPct }}%)
                </div>
                <div class="sb-metric-lbl">Net Profit / Loss</div>
            </div>
            <!-- 5. Total Equity -->
            <div class="sb-metric-col" style="text-align:right;">
                <div class="sb-metric-num">{{ number_format($totalEquity, 0, '.', ',') }}</div>
                <div class="sb-metric-lbl">Total Equity</div>
            </div>
        </div>

        <!-- 3. Main White Card Panel (kukLdZ) -->
        <div id="portfolio-section" class="sb-main-card">

            <!-- Subheader Bar: Filter Buttons (Stocks 0%, Bonds 0%, Performance) -->
            <div class="sb-card-subheader">
                <div class="sb-filter-group">
                    <!-- Stocks 0% -->
                    <button class="sb-filter-btn">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#667085" stroke-width="2" stroke-linecap="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
                        <span>Stocks</span>
                        <div class="sb-filter-badge">{{ $totalEquity > 0 ? round(($invested / $totalEquity) * 100) : 0 }}%</div>
                    </button>
                    <!-- Bonds 0% -->
                    <button class="sb-filter-btn" style="opacity:0.8;">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#667085" stroke-width="2" stroke-linecap="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                        <span>Bonds</span>
                        <div class="sb-filter-badge">0%</div>
                    </button>
                    <!-- All Portfolio 0% -->
                    <button class="sb-filter-btn">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#667085" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10h-10z"/></svg>
                        <span>All Portfolio</span>
                        <div class="sb-filter-badge">{{ $totalEquity > 0 ? round(($invested / $totalEquity) * 100) : 0 }}%</div>
                    </button>

                    <!-- Performance Button (Official Purple Gradient SVG) -->
                    <a href="#history-section" class="sb-perf-btn">
                        <svg width="20" height="14" viewBox="0 0 20 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M0 4a4 4 0 0 1 4-4h12a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4H4a4 4 0 0 1-4-4z" fill="url(#performance-gradient)" fill-opacity=".8"/>
                            <path d="m14.813 4.375-4.157 4.156L8.47 6.344 5.188 9.625" stroke="#fff" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M12.188 4.375h2.624V7" stroke="#fff" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                            <defs>
                                <linearGradient id="performance-gradient" x1="-1.667" y1="-.778" x2="13.192" y2="20.967" gradientUnits="userSpaceOnUse">
                                    <stop offset=".192" stop-color="#8228BD"/>
                                    <stop offset="1" stop-color="#2073AC"/>
                                </linearGradient>
                            </defs>
                        </svg>
                        <span>Performance</span>
                    </a>
                </div>

                <!-- 3 vertical dots -->
                <div style="color:#B5B5B5; font-size:18px; font-weight:bold; cursor:pointer; padding:0 4px;">⋮</div>
            </div>

            <div class="sb-card-body">
                <!-- ═════════════════════════════════════════════════ -->
                <!-- TOP 3-COLUMN PERFORMANCE VIEW                     -->
                <!-- ═════════════════════════════════════════════════ -->
                <div class="sb-performance-grid">

                    <!-- ── KOLOM 1: TOTAL EQUITY & CUMULATIVE RETURN VS IHSG ── -->
                    <div style="display:flex; flex-direction:column; gap:16px;">

                        <!-- Card 1: Total Equity -->
                        <div class="sb-box">
                            <div class="sb-box-title">Total Equity</div>
                            <div class="sb-box-num">
                                Rp<span x-text="formatNumber(currentDisplayEquity)">{{ number_format($totalEquity, 0, '.', ',') }}</span>
                            </div>

                            <!-- Canvas Chart -->
                            <div style="height:180px; width:100%; position:relative;">
                                <canvas x-ref="equityChartCanvas"></canvas>
                            </div>

                            <!-- Range Selector -->
                            <div class="sb-range-selector">
                                <template x-for="r in ['1W','1M','3M','YTD','1Y','All']" :key="r">
                                    <button type="button"
                                            class="sb-range-opt"
                                            :class="equityRange === r ? 'active' : ''"
                                            @click="setEquityRange(r)"
                                            x-text="r">
                                    </button>
                                </template>
                            </div>
                        </div>

                        <!-- Card 2: Cumulative Portfolio Return vs IHSG -->
                        <div class="sb-box">
                            <div class="sb-box-title" style="margin-bottom:8px;">
                                <span>Cumulative Portfolio Return</span>
                                <span style="color:#969696; font-size:12px; cursor:pointer;" title="Perbandingan return persentase portofolio terhadap IHSG">ⓘ</span>
                            </div>

                            <!-- Legend Bar -->
                            <div class="sb-legend-split-box">
                                <div class="sb-legend-half">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="width:3px; height:12px; background:#00AB6B; border-radius:2px;"></span>
                                        <span style="color:#667085; font-size:12px; font-weight:500;">Portfolio</span>
                                    </div>
                                    <span style="font-weight:700; font-size:12px;" :class="portfolioReturnPct >= 0 ? 'c-green' : 'c-red'" x-text="(portfolioReturnPct >= 0 ? '+' : '') + portfolioReturnPct.toFixed(2) + '%'"></span>
                                </div>
                                <div class="sb-legend-divider"></div>
                                <div class="sb-legend-half">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="width:3px; height:12px; background:#8228BD; border-radius:2px;"></span>
                                        <span style="color:#667085; font-size:12px; font-weight:500;">IHSG</span>
                                    </div>
                                    <span style="font-weight:700; font-size:12px;" :class="ihsgReturnPct >= 0 ? 'c-green' : 'c-red'" x-text="(ihsgReturnPct !== null ? (ihsgReturnPct >= 0 ? '+' : '') + ihsgReturnPct.toFixed(2) + '%' : '—')"></span>
                                </div>
                            </div>

                            <!-- Canvas Chart -->
                            <div style="height:180px; width:100%; position:relative;">
                                <canvas x-ref="compareChartCanvas"></canvas>
                            </div>

                            <!-- Range Selector -->
                            <div class="sb-range-selector">
                                <template x-for="r in ['1W','1M','3M','YTD','1Y','All']" :key="r">
                                    <button type="button"
                                            class="sb-range-opt"
                                            :class="compareRange === r ? 'active' : ''"
                                            @click="setCompareRange(r)"
                                            x-text="r">
                                    </button>
                                </template>
                            </div>
                        </div>

                    </div>

                    <!-- ── KOLOM 2: TOTAL EQUITY RETURN (TABEL HARIAN) ── -->
                    <div class="sb-box" style="display:flex; flex-direction:column;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div class="sb-box-title">
                                <span>Total Equity Return</span>
                                <span style="color:#969696; font-size:12px; cursor:pointer;">ⓘ</span>
                            </div>
                            <div class="sb-dropdown-pill">
                                <span>Last 1 Month</span>
                                <span style="font-size:10px; color:#667085;">▾</span>
                            </div>
                        </div>

                        <!-- Toggle Pills -->
                        <div class="sb-toggle-pills">
                            <button type="button" class="sb-pill-active">Daily</button>
                            <button type="button" class="sb-pill-inactive">Monthly</button>
                        </div>

                        <!-- Scrollable Table -->
                        <div class="sb-scroll-area" style="flex:1;">
                            <table class="sb-table">
                                <thead>
                                    <tr>
                                        <th style="width:25%; text-align:left;">Date</th>
                                        <th style="width:35%; text-align:center;">Equity</th>
                                        <th style="width:40%; text-align:right;">P&amp;L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    @forelse($portfolioReport['daily_equity_table'] as $row)
                                    <tr>
                                        <td style="color:#333333; font-weight:500; text-align:left;">
                                            {{ \Carbon\Carbon::parse($row['date'])->format('j M y') }}
                                        </td>
                                        <td style="text-align:center; font-weight:500; color:#111111;">
                                            {{ number_format($row['equity'], 0, '.', ',') }}
                                        </td>
                                        <td style="text-align:right; font-weight:600;" class="{{ $row['pnl'] > 0 ? 'c-green' : ($row['pnl'] < 0 ? 'c-red' : 'c-gray') }}">
                                            @if($row['pnl'] > 0)
                                                +{{ number_format($row['pnl'], 0, '.', ',') }} (+{{ $row['pnl_pct'] }}%)
                                            @elseif($row['pnl'] < 0)
                                                {{ number_format($row['pnl'], 0, '.', ',') }} ({{ $row['pnl_pct'] }}%)
                                            @else
                                                0 (0.00%)
                                            @endif
                                        </td>
                                    </tr>
                                    @empty
                                    <tr>
                                        <td colspan="3" style="text-align:center; padding:24px; color:#98A2B3;">Belum ada histori harian.</td>
                                    </tr>
                                    @endforelse
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- ── KOLOM 3: PORTFOLIO ALLOCATION (DONUT CHARTS) ── -->
                    <div class="sb-box" style="display:flex; flex-direction:column;">
                        <div class="sb-box-title">Portfolio Allocation</div>

                        <!-- Toggle Pills -->
                        <div class="sb-toggle-pills">
                            <button type="button" class="sb-pill-active">Stocks</button>
                            <button type="button" class="sb-pill-inactive">Sub-Sector</button>
                        </div>

                        <!-- Donut Ring Chart Container -->
                        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; margin: 32px auto 20px; position:relative; width:210px; height:210px;">
                            <canvas x-ref="allocationChartCanvas" width="210" height="210"></canvas>
                            <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none;">
                                <div style="font-size:13px; font-weight:500; color:#666666;">
                                    {{ count($portfolioReport['allocation']) }} Stock
                                </div>
                            </div>
                        </div>

                        <!-- Stock Holdings list below with Official Logos -->
                        @if(count($portfolioReport['allocation']) > 0)
                        <div style="width:100%; margin-top:20px; border-top:1px solid #F2F4F7; padding-top:12px;">
                            @foreach($portfolioReport['allocation'] as $item)
                            @php
                                $logo = $stockLogos[$item['ticker']] ?? null;
                                $initial = substr($item['ticker'], 0, 2);
                            @endphp
                            <div style="display:flex; justify-content:space-between; align-items:center; padding:7px 0; font-size:12px;">
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <div style="width:24px; height:24px; border-radius:50%; border:1px solid #E4E7EC; background:#FFFFFF; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0;">
                                        @if($logo)
                                            <img src="{{ $logo }}" alt="{{ $item['ticker'] }}" style="width:100%; height:100%; object-fit:contain; padding:2px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                                            <span style="display:none; width:100%; height:100%; background:#101828; color:#FFF; font-size:9px; font-weight:800; align-items:center; justify-content:center;">{{ $initial }}</span>
                                        @else
                                            <span style="width:100%; height:100%; background:#101828; color:#FFF; font-size:9px; font-weight:800; display:flex; align-items:center; justify-content:center;">{{ $initial }}</span>
                                        @endif
                                    </div>
                                    <div style="display:flex; align-items:baseline; gap:4px;">
                                        <span style="font-weight:700; color:#101828;">{{ $item['ticker'] }}</span>
                                        <span style="font-size:10px; color:#98A2B3;">({{ $item['positions'] }} pos)</span>
                                    </div>
                                </div>
                                <div style="text-align:right;">
                                    <div style="font-weight:700; color:#101828;">{{ $item['pct'] }}%</div>
                                    <div style="font-size:10px; color:#98A2B3;">Rp{{ number_format($item['value'], 0, '.', ',') }}</div>
                                </div>
                            </div>
                            @endforeach
                        </div>
                        @endif
                    </div>

                </div>

                <!-- ═════════════════════════════════════════════════ -->
                <!-- DIVIDER LINE                                      -->
                <!-- ═════════════════════════════════════════════════ -->
                <div class="sb-section-divider"></div>

                <!-- ═════════════════════════════════════════════════ -->
                <!-- TRADE SUMMARY SECTION (GAMBAR 2)                  -->
                <!-- ═════════════════════════════════════════════════ -->
                <div id="history-section">
                    <!-- Section Header -->
                    <div class="sb-trade-summary-hdr">
                        <span class="sb-trade-summary-title">Trade Summary</span>
                        <div class="sb-dropdown-pill">
                            <span>Month to Date</span>
                            <span style="font-size:10px; color:#667085;">▾</span>
                        </div>
                    </div>

                    <div class="sb-history-grid">

                        <!-- ── KOLOM KIRI: WIN RATE GAUGE, SPLIT METRICS & TOP GAINERS ── -->
                        <div style="display:flex; flex-direction:column; gap:16px;">

                            <!-- Box 1: Gauge & Stats -->
                            <div class="sb-box">
                                <!-- Top Speedometer Row -->
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; align-items:center; padding-bottom:16px; border-bottom:1px solid #F0F2F5;">
                                    <!-- Semi-Circle Gauge -->
                                    <div style="display:flex; flex-direction:column; align-items:center;">
                                        <div style="width:160px; height:85px; position:relative;">
                                            <canvas x-ref="gaugeChartCanvas"></canvas>
                                            <div style="position:absolute; bottom:0; left:0; right:0; text-align:center;">
                                                <div style="font-size:22px; font-weight:800; color:#111111; line-height:1;">{{ $stats['closed'] }}</div>
                                                <div style="font-size:10px; font-weight:600; color:#969696; text-transform:uppercase; margin-top:2px;">Trades</div>
                                            </div>
                                        </div>
                                        <div style="display:flex; justify-content:space-between; width:150px; font-size:11px; font-weight:700; margin-top:8px;">
                                            <span class="c-green">{{ $stats['win'] }} <span style="font-weight:400; color:#667085;">Wins</span></span>
                                            <span class="c-red">{{ $stats['loss'] }} <span style="font-weight:400; color:#667085;">Losses</span></span>
                                        </div>
                                    </div>

                                    <!-- Win Rate & Profit Factor Column -->
                                    <div style="border-left:1px solid #F0F2F5; padding-left:16px;">
                                        <div>
                                            <div style="font-size:11px; font-weight:500; color:#667085;">Win Rate</div>
                                            <div style="font-size:24px; font-weight:800; color:#00AA5B; line-height:1.2; margin-top:2px;">
                                                {{ $stats['win_rate'] }}%
                                            </div>
                                        </div>
                                        <div style="margin-top:10px;">
                                            <div style="font-size:11px; font-weight:500; color:#667085; display:flex; align-items:center; gap:4px;">
                                                <span>Profit Factor</span>
                                                <span style="color:#969696; font-size:10px;">ⓘ</span>
                                            </div>
                                            <div style="font-size:20px; font-weight:700; color:#111111; margin-top:2px;">
                                                {{ $portfolioReport['profit_factor'] !== null ? number_format($portfolioReport['profit_factor'], 2) : '—' }}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Mid Row: Transaction Value & Orders -->
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; padding:12px 0; border-bottom:1px solid #F0F2F5; font-size:12px;">
                                    <div>
                                        <div style="font-size:11px; color:#667085;">Total Transaction Value</div>
                                        <div style="font-size:14px; font-weight:700; color:#111111; margin-top:2px;">
                                            Rp{{ number_format($portfolioReport['total_transaction_value'], 0, '.', ',') }}
                                        </div>
                                    </div>
                                    <div>
                                        <div style="font-size:11px; color:#667085;">Total Orders</div>
                                        <div style="font-size:14px; font-weight:700; color:#111111; margin-top:2px;">
                                            {{ $portfolioReport['total_orders'] }}
                                        </div>
                                    </div>
                                </div>

                                <!-- Bottom Split: Profit vs Loss -->
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; padding-top:14px; font-size:12px;">
                                    <!-- Profit Side -->
                                    <div>
                                        <div style="font-weight:700; color:#111111; margin-bottom:8px;">Profit</div>
                                        <div style="margin-bottom:6px;">
                                            <div style="font-size:10px; color:#667085;">Max Profit</div>
                                            <div style="font-weight:700; color:#00AA5B; display:flex; align-items:center; gap:3px;">
                                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AA5B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                <span>Rp{{ number_format($portfolioReport['max_profit_trade']->pnl_total ?? 0, 0, '.', ',') }}</span>
                                            </div>
                                        </div>
                                        <div style="margin-bottom:6px;">
                                            <div style="font-size:10px; color:#667085;">Max Profit %</div>
                                            <div style="font-weight:700; color:#00AA5B;">
                                                +{{ number_format($portfolioReport['max_profit_pct'] ?? 0, 2) }}%
                                            </div>
                                        </div>
                                        <div>
                                            <div style="font-size:10px; color:#667085;">Avg. Profit</div>
                                            <div style="font-weight:700; color:#00AA5B; display:flex; align-items:center; gap:3px;">
                                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AA5B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                <span>Rp{{ number_format($portfolioReport['avg_profit'] ?? 0, 0, '.', ',') }}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Loss Side -->
                                    <div style="border-left:1px solid #F0F2F5; padding-left:16px;">
                                        <div style="font-weight:700; color:#111111; margin-bottom:8px;">Loss</div>
                                        <div style="margin-bottom:6px;">
                                            <div style="font-size:10px; color:#667085;">Max Loss</div>
                                            <div style="font-weight:700; color:#EE4A49; display:flex; align-items:center; gap:3px;">
                                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                <span>Rp{{ number_format(abs($portfolioReport['max_loss_trade']->pnl_total ?? 0), 0, '.', ',') }}</span>
                                            </div>
                                        </div>
                                        <div style="margin-bottom:6px;">
                                            <div style="font-size:10px; color:#667085;">Max Loss %</div>
                                            <div style="font-weight:700; color:#EE4A49;">
                                                {{ number_format($portfolioReport['max_loss_pct'] ?? 0, 2) }}%
                                            </div>
                                        </div>
                                        <div>
                                            <div style="font-size:10px; color:#667085;">Avg. Loss</div>
                                            <div style="font-weight:700; color:#EE4A49; display:flex; align-items:center; gap:3px;">
                                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                <span>Rp{{ number_format(abs($portfolioReport['avg_loss'] ?? 0), 0, '.', ',') }}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Box 2: Top Gainer / Loser Table -->
                            <div class="sb-box" x-data="{ leaderTab: 'gainers' }">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                                    <div class="sb-dropdown-pill" style="padding:4px 10px;">
                                        <select x-model="leaderTab" style="border:none; outline:none; font-size:12px; font-weight:700; color:#111111; background:transparent; cursor:pointer;">
                                            <option value="gainers">Top Gainer (Rp) ▾</option>
                                            <option value="losers">Top Loser (Rp) ▾</option>
                                        </select>
                                    </div>
                                </div>

                                <div class="sb-scroll-area" style="max-height:280px;">
                                    <table class="sb-table" style="table-layout:fixed; width:100%;">
                                        <thead>
                                            <tr>
                                                <th style="width:42%; text-align:left;">Code</th>
                                                <th style="width:15%; text-align:center;">Trades</th>
                                                <th style="width:43%; text-align:right;">P&amp;L</th>
                                            </tr>
                                        </thead>
                                        <tbody x-show="leaderTab === 'gainers'">
                                            @forelse($topGainers as $g)
                                            @php
                                                $logo = $stockLogos[$g['ticker']] ?? null;
                                                $initial = substr($g['ticker'], 0, 2);
                                                $isProfit = ($g['pnl'] ?? 0) >= 0;
                                            @endphp
                                            <tr>
                                                <td style="width:42%;">
                                                    <div style="display:flex; align-items:center; gap:8px;">
                                                        <div style="width:22px; height:22px; border-radius:50%; border:1px solid #E5E7EB; background:#FFFFFF; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0;">
                                                            @if($logo)
                                                                <img src="{{ $logo }}" alt="{{ $g['ticker'] }}" style="width:100%; height:100%; object-fit:contain; padding:2px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                                                                <span style="display:none; width:100%; height:100%; background:#101828; color:#FFFFFF; font-size:8px; font-weight:800; align-items:center; justify-content:center;">{{ $initial }}</span>
                                                            @else
                                                                <span style="width:100%; height:100%; background:#101828; color:#FFFFFF; font-size:8px; font-weight:800; display:flex; align-items:center; justify-content:center;">{{ $initial }}</span>
                                                            @endif
                                                        </div>
                                                        <span style="font-weight:700; color:#111111; font-size:12px; white-space:nowrap;">{{ $g['ticker'] }}</span>
                                                    </div>
                                                </td>
                                                <td style="width:15%; text-align:center; color:#667085; font-size:12px; white-space:nowrap;">{{ $g['trades'] }}</td>
                                                <td style="width:43%; text-align:right; font-weight:600; font-size:12px; white-space:nowrap;" class="{{ $isProfit ? 'c-green' : 'c-red' }}">
                                                    @if($isProfit)
                                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="display:inline; vertical-align:middle;"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AB6B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                        {{ number_format($g['pnl'], 0, '.', ',') }}
                                                        <span style="font-size:10px; font-weight:400; opacity:0.85;">(+{{ $g['pnl_pct'] }}%)</span>
                                                    @else
                                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="display:inline; vertical-align:middle;"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                        {{ number_format(abs($g['pnl']), 0, '.', ',') }}
                                                        <span style="font-size:10px; font-weight:400; opacity:0.85;">({{ $g['pnl_pct'] }}%)</span>
                                                    @endif
                                                </td>
                                            </tr>
                                            @empty
                                            <tr>
                                                <td colspan="3" style="text-align:center; padding:16px; color:#98A2B3;">Belum ada riwayat transaksi.</td>
                                            </tr>
                                            @endforelse
                                        </tbody>
                                        <tbody x-show="leaderTab === 'losers'">
                                            @forelse($topLosers as $l)
                                            @php
                                                $logo = $stockLogos[$l['ticker']] ?? null;
                                                $initial = substr($l['ticker'], 0, 2);
                                                $isProfit = ($l['pnl'] ?? 0) >= 0;
                                            @endphp
                                            <tr>
                                                <td style="width:42%;">
                                                    <div style="display:flex; align-items:center; gap:8px;">
                                                        <div style="width:22px; height:22px; border-radius:50%; border:1px solid #E5E7EB; background:#FFFFFF; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0;">
                                                            @if($logo)
                                                                <img src="{{ $logo }}" alt="{{ $l['ticker'] }}" style="width:100%; height:100%; object-fit:contain; padding:2px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                                                                <span style="display:none; width:100%; height:100%; background:#101828; color:#FFFFFF; font-size:8px; font-weight:800; align-items:center; justify-content:center;">{{ $initial }}</span>
                                                            @else
                                                                <span style="width:100%; height:100%; background:#101828; color:#FFFFFF; font-size:8px; font-weight:800; display:flex; align-items:center; justify-content:center;">{{ $initial }}</span>
                                                            @endif
                                                        </div>
                                                        <span style="font-weight:700; color:#111111; font-size:12px; white-space:nowrap;">{{ $l['ticker'] }}</span>
                                                    </div>
                                                </td>
                                                <td style="width:15%; text-align:center; color:#667085; font-size:12px; white-space:nowrap;">{{ $l['trades'] }}</td>
                                                <td style="width:43%; text-align:right; font-weight:600; font-size:12px; white-space:nowrap;" class="{{ $isProfit ? 'c-green' : 'c-red' }}">
                                                    @if($isProfit)
                                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="display:inline; vertical-align:middle;"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AB6B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                        {{ number_format($l['pnl'], 0, '.', ',') }}
                                                        <span style="font-size:10px; font-weight:400; opacity:0.85;">(+{{ $l['pnl_pct'] }}%)</span>
                                                    @else
                                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="display:inline; vertical-align:middle;"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                                        {{ number_format(abs($l['pnl']), 0, '.', ',') }}
                                                        <span style="font-size:10px; font-weight:400; opacity:0.85;">({{ $l['pnl_pct'] }}%)</span>
                                                    @endif
                                                </td>
                                            </tr>
                                            @empty
                                            <tr>
                                                <td colspan="3" style="text-align:center; padding:16px; color:#98A2B3;">Belum ada riwayat transaksi.</td>
                                            </tr>
                                            @endforelse
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                        </div>

                        <!-- ── KOLOM KANAN: REALIZED P&L TRAJECTORY CURVE (GAMBAR 2) ── -->
                        <div class="sb-box">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                <div>
                                    <div class="sb-box-title">
                                        <span>Total Realized {{ $stats['total_pnl'] >= 0 ? 'Gain' : 'Loss' }}</span>
                                        <span style="color:#969696; font-size:12px;">ⓘ</span>
                                    </div>
                                    <div class="sb-box-num" style="color: {{ $stats['total_pnl'] >= 0 ? '#00AB6B' : '#EE4A49' }}; font-size:24px;">
                                        {{ $stats['total_pnl'] >= 0 ? '+' : '-' }}Rp{{ number_format(abs($stats['total_pnl']), 0, '.', ',') }}
                                        <span style="font-size:11px; font-weight:400; color:#969696; vertical-align:middle; margin-left:6px;">Month to Date</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Canvas Realized Curve Chart -->
                            <div style="height:250px; width:100%; position:relative; margin-top:12px;">
                                <canvas x-ref="realizedChartCanvas"></canvas>
                            </div>

                            <!-- Bottom Summary Breakdown -->
                            <div style="border-top:1px solid #F0F2F5; padding-top:14px; margin-top:14px; font-size:12px; display:flex; flex-direction:column; gap:8px;">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="color:#475467; font-weight:500;">Total Stocks Realized {{ $stats['total_pnl'] >= 0 ? 'Gain' : 'Loss' }}</span>
                                    <span style="font-weight:700; display:flex; align-items:center; gap:3px;" class="{{ $stats['total_pnl'] >= 0 ? 'c-green' : 'c-red' }}">
                                        @if($stats['total_pnl'] >= 0)
                                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AB6B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                        @else
                                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                        @endif
                                        <span>Rp{{ number_format(abs($stats['total_pnl']), 0, '.', ',') }}</span>
                                    </span>
                                </div>
                                <div style="border-left:2px solid #E5E7EB; padding-left:10px; margin:2px 0 2px 6px; display:flex; flex-direction:column; gap:6px;">
                                    <div style="display:flex; justify-content:space-between; align-items:center;">
                                        <span style="color:#667085;">Realized Gain</span>
                                        <span style="font-weight:700; color:#00AA5B; display:flex; align-items:center; gap:3px;">
                                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 11.33L11.34 4.67M4.67 4.67L11.34 4.67L11.34 11.33" stroke="#00AA5B" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                            <span>Rp{{ number_format($portfolioReport['realized_gain'], 0, '.', ',') }}</span>
                                        </span>
                                    </div>
                                    <div style="display:flex; justify-content:space-between; align-items:center;">
                                        <span style="color:#667085;">Realized Loss</span>
                                        <span style="font-weight:700; color:#EE4A49; display:flex; align-items:center; gap:3px;">
                                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.67 4.67L11.34 11.33M11.34 4.67L11.34 11.33L4.67 11.33" stroke="#EE4A49" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                            <span>Rp{{ number_format($portfolioReport['realized_loss'], 0, '.', ',') }}</span>
                                        </span>
                                    </div>
                                </div>
                                <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #F0F2F5; padding-top:8px;">
                                    <span style="color:#969696;">Total Dividend Received</span>
                                    <span style="font-weight:500; color:#969696;">Rp0</span>
                                </div>
                            </div>
                        </div>

                    </div>

                </div>

            </div>

        </div>

    </main>

    <!-- ═════════════════════════════════════════════════════════ -->
    <!-- CHART SCRIPTS (Exact Stockbit Visual Styling)             -->
    <!-- ═════════════════════════════════════════════════════════ -->
    <script>
        document.addEventListener('alpine:init', () => {
            Alpine.data('stockbitPortfolioApp', (initData) => ({
                // Charts instances
                equityChart: null,
                compareChart: null,
                allocationChart: null,
                gaugeChart: null,
                realizedChart: null,

                // Range states
                equityRange: 'YTD',
                compareRange: 'YTD',

                currentDisplayEquity: initData.currentEquity,
                portfolioReturnPct: 0,
                ihsgReturnPct: null,

                init() {
                    this.$nextTick(() => {
                        this.renderAllCharts();
                    });
                },

                renderAllCharts() {
                    this.renderEquityChart();
                    this.renderCompareChart();
                    this.renderAllocationChart();
                    this.renderGaugeChart();
                    this.renderRealizedChart();
                },

                formatNumber(val) {
                    return Math.round(val).toLocaleString('en-US');
                },

                formatShortVal(val) {
                    const abs = Math.abs(val);
                    if (abs >= 1_000_000_000) return (val / 1_000_000_000).toFixed(1) + 'B';
                    if (abs >= 1_000_000) return (val / 1_000_000).toFixed(1) + 'M';
                    if (abs >= 1_000) return (val / 1_000).toFixed(0) + 'K';
                    return String(Math.round(val));
                },

                getStartIndex(range) {
                    const dates = initData.chart.dates || [];
                    if (dates.length === 0 || range === 'All') return 0;
                    const lastDate = new Date(dates[dates.length - 1] + 'T00:00:00');
                    let cutoff = new Date(lastDate);
                    switch (range) {
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

                // ── 1. TOTAL EQUITY CHART ──
                setEquityRange(r) {
                    this.equityRange = r;
                    if (this.equityChart) this.equityChart.destroy();
                    this.renderEquityChart();
                },

                renderEquityChart() {
                    const startIdx = this.getStartIndex(this.equityRange);
                    const labels = (initData.chart.labels || []).slice(startIdx);
                    const equity = (initData.chart.portfolioRp || []).slice(startIdx);
                    this.currentDisplayEquity = equity.length ? equity[equity.length - 1] : initData.currentEquity;

                    const ctx = this.$refs.equityChartCanvas.getContext('2d');
                    const gradient = ctx.createLinearGradient(0, 0, 0, 180);
                    gradient.addColorStop(0, 'rgba(0, 171, 107, 0.25)');
                    gradient.addColorStop(1, 'rgba(0, 171, 107, 0.0)');

                    this.equityChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                data: equity,
                                borderColor: '#00AB6B',
                                backgroundColor: gradient,
                                fill: true,
                                tension: 0.3,
                                borderWidth: 1.5,
                                pointRadius: 0,
                                pointHoverRadius: 4,
                                pointHoverBackgroundColor: '#00AB6B',
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: '#101828',
                                    callbacks: {
                                        label: (c) => 'Rp' + Math.round(c.parsed.y).toLocaleString('en-US')
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    grid: { display: false },
                                    ticks: { color: '#B5B5B5', font: { size: 11 }, maxTicksLimit: 5 }
                                },
                                y: {
                                    position: 'right',
                                    grid: { color: '#F0F2F5' },
                                    ticks: {
                                        color: '#B5B5B5',
                                        font: { size: 11 },
                                        callback: (v) => this.formatShortVal(v)
                                    }
                                }
                            }
                        }
                    });
                },

                // ── 2. CUMULATIVE RETURN VS IHSG CHART ──
                setCompareRange(r) {
                    this.compareRange = r;
                    if (this.compareChart) this.compareChart.destroy();
                    this.renderCompareChart();
                },

                renderCompareChart() {
                    const startIdx = this.getStartIndex(this.compareRange);
                    const labels = (initData.chart.labels || []).slice(startIdx);
                    const portPct = (initData.chart.portfolioPct || []).slice(startIdx);
                    const ihsgPct = (initData.chart.ihsgPct || []).slice(startIdx);

                    this.portfolioReturnPct = portPct.length ? portPct[portPct.length - 1] : 0;
                    this.ihsgReturnPct = ihsgPct.length ? ihsgPct[ihsgPct.length - 1] : null;

                    const ctx = this.$refs.compareChartCanvas.getContext('2d');
                    this.compareChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [
                                {
                                    label: 'Portfolio',
                                    data: portPct,
                                    borderColor: '#00AB6B',
                                    backgroundColor: 'transparent',
                                    borderWidth: 1.5,
                                    tension: 0.3,
                                    pointRadius: 0
                                },
                                {
                                    label: 'IHSG',
                                    data: ihsgPct,
                                    borderColor: '#8228BD',
                                    backgroundColor: 'transparent',
                                    borderWidth: 1.5,
                                    tension: 0.3,
                                    pointRadius: 0
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: '#101828',
                                    callbacks: {
                                        label: (c) => c.dataset.label + ': ' + (c.parsed.y >= 0 ? '+' : '') + c.parsed.y.toFixed(2) + '%'
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    grid: { display: false },
                                    ticks: { color: '#B5B5B5', font: { size: 11 }, maxTicksLimit: 5 }
                                },
                                y: {
                                    position: 'right',
                                    grid: {
                                        color: (context) => (context.tick && context.tick.value === 0) ? '#D0D5DD' : '#F0F2F5',
                                        borderDash: (context) => (context.tick && context.tick.value === 0) ? [4, 4] : []
                                    },
                                    ticks: {
                                        color: '#B5B5B5',
                                        font: { size: 11 },
                                        callback: (v) => v.toFixed(0) + '%'
                                    }
                                }
                            }
                        }
                    });
                },

                // ── 3. PORTFOLIO ALLOCATION DOUGHNUT ──
                renderAllocationChart() {
                    const ctx = this.$refs.allocationChartCanvas.getContext('2d');
                    const allocations = initData.allocation || [];
                    const palette = ['#00AB6B', '#8228BD', '#0BA5EC', '#EE46BC', '#F79009', '#EE4A49'];

                    this.allocationChart = new Chart(ctx, {
                        type: 'doughnut',
                        data: {
                            labels: allocations.length ? allocations.map(a => a.ticker) : ['Cash'],
                            datasets: [{
                                data: allocations.length ? allocations.map(a => a.value) : [1],
                                backgroundColor: allocations.length ? allocations.map((_, i) => palette[i % palette.length]) : ['#CBCBCB'],
                                borderWidth: 0
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            cutout: '84%',
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    callbacks: {
                                        label: (c) => {
                                            if (!allocations.length) return '100% Cash';
                                            const item = allocations[c.dataIndex];
                                            return item.ticker + ': Rp' + item.value.toLocaleString('en-US') + ' (' + item.pct + '%)';
                                        }
                                    }
                                }
                            }
                        }
                    });
                },

                // ── 4. WIN RATE SPEEDOMETER GAUGE ──
                renderGaugeChart() {
                    const ctx = this.$refs.gaugeChartCanvas.getContext('2d');
                    const wins = initData.winCount;
                    const losses = initData.lossCount;
                    const total = wins + losses;

                    this.gaugeChart = new Chart(ctx, {
                        type: 'doughnut',
                        data: {
                            labels: ['Wins', 'Losses'],
                            datasets: [{
                                data: total > 0 ? [wins, losses] : [1, 1],
                                backgroundColor: total > 0 ? ['#00AB6B', '#EE4A49'] : ['#E5E7EB', '#E5E7EB'],
                                borderWidth: 0
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            rotation: -90,
                            circumference: 180,
                            cutout: '78%',
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    callbacks: {
                                        label: (c) => c.label + ': ' + c.parsed
                                    }
                                }
                            }
                        }
                    });
                },

                // ── 5. REALIZED P&L TRAJECTORY CURVE (Smooth Area Chart persis Stockbit) ──
                renderRealizedChart() {
                    const ctx = this.$refs.realizedChartCanvas.getContext('2d');
                    const labels = initData.chart.labels || [];
                    const curve = initData.realizedCurve || [];

                    const lastVal = curve.length ? curve[curve.length - 1] : 0;
                    const isProfit = lastVal >= 0;
                    const strokeColor = isProfit ? '#00AB6B' : '#EE4A49';

                    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
                    if (isProfit) {
                        gradient.addColorStop(0, 'rgba(0, 171, 107, 0.25)');
                        gradient.addColorStop(1, 'rgba(0, 171, 107, 0.0)');
                    } else {
                        gradient.addColorStop(0, 'rgba(238, 74, 73, 0.25)');
                        gradient.addColorStop(0.6, 'rgba(238, 74, 73, 0.08)');
                        gradient.addColorStop(1, 'rgba(238, 74, 73, 0.0)');
                    }

                    this.realizedChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: 'Realized PnL',
                                data: curve,
                                borderColor: strokeColor,
                                backgroundColor: gradient,
                                fill: true,
                                tension: 0.3,
                                borderWidth: 1.5,
                                pointRadius: 0
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: '#101828',
                                    callbacks: {
                                        label: (c) => (c.parsed.y >= 0 ? '+Rp' : '-Rp') + Math.abs(Math.round(c.parsed.y)).toLocaleString('en-US')
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    grid: { display: false },
                                    ticks: { color: '#B5B5B5', font: { size: 10 }, maxTicksLimit: 6 }
                                },
                                y: {
                                    position: 'right',
                                    grid: { color: '#F0F2F5' },
                                    ticks: {
                                        color: '#B5B5B5',
                                        font: { size: 10 },
                                        callback: (v) => (v >= 0 ? '+' : '-') + this.formatShortVal(Math.abs(v))
                                    }
                                }
                            }
                        }
                    });
                }
            }));
        });
    </script>
</body>
</html>
