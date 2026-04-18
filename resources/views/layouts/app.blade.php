<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">

    <title>{{ config('app.name', 'Sentimena') }}</title>

    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap">
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="trade-dark-ui" x-data="{ sidebarOpen: false }">
    <div class="min-h-screen flex">
        {{-- Sidebar --}}
        <aside class="app-sidebar hidden lg:flex lg:flex-col w-[200px] fixed inset-y-0">
            <div class="px-4 py-4 flex items-center gap-3 border-b border-white/10">
                <div class="app-logo-mark h-10 w-10 flex items-center justify-center">
                    SI
                </div>
                <div>
                    <div class="app-brand-kicker">Sentimena</div>
                    <div class="app-brand-title">IDX Sentiment</div>
                </div>
            </div>
            <nav class="flex-1 px-0 py-4 space-y-1 text-sm">
                @php
                    $nav = [
                        ['label' => 'Dashboard', 'route' => 'dashboard', 'href' => route('dashboard'), 'icon' => 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001 1h4a1 1 0 001-1m-6 0V9m0 12h6'],
                        ['label' => 'Berita Terkini', 'route' => 'news.index', 'href' => route('news.index'), 'icon' => 'M4 6h16M4 10h16M4 14h10m-4 4h4'],
                        ['label' => 'Watchlist', 'route' => 'watchlist.index', 'href' => route('watchlist.index'), 'icon' => 'M5 4h14a1 1 0 011 1v10a1 1 0 01-.553.894l-6.894 3.447a1 1 0 01-.894 0L4.765 15.96A1 1 0 014 15V5a1 1 0 011-1z'],
                        ['label' => 'Prediksi', 'route' => 'analytics.index', 'href' => route('analytics.index'), 'icon' => 'M3 17l6-6 4 4 8-8'],
                        ['label' => 'Evaluasi Model', 'route' => 'evaluasi.index', 'href' => route('evaluasi.index'), 'icon' => 'M9 17v-6h6v6m-7 4h8a2 2 0 002-2v-8l-5-5H9a2 2 0 00-2 2v11a2 2 0 002 2z'],
                        ['label' => 'Evaluasi Sentimen', 'route' => 'evaluasi.sentimen', 'href' => route('evaluasi.sentimen'), 'icon' => 'M12 8c1.656 0 3-1.567 3-3.5S13.656 1 12 1 9 2.567 9 4.5 10.344 8 12 8zm0 0v6m0 0l-4 9m4-9l4 9'],
                        ['label' => 'Backtest DSS', 'route' => 'backtest.index', 'href' => route('backtest.index'), 'icon' => 'M4 12h16m-8-8v16'],
                        ['label' => 'Evaluasi Sistem', 'route' => 'evaluation.index', 'href' => route('evaluation.index'), 'icon' => 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4'],
                        ['label' => 'Trade Journal', 'route' => 'trades.index', 'href' => route('trades.index'), 'icon' => 'M9 7h6m-6 4h6m-9 4h12M5 5a2 2 0 012-2h10a2 2 0 012 2v14a2 2 0 01-2 2H7a2 2 0 01-2-2V5z'],
                    ];
                @endphp
                @foreach($nav as $item)
                    @php $active = request()->routeIs($item['route']); @endphp
                    <a href="{{ $item['href'] }}"
                       class="app-nav-item {{ $active ? 'app-nav-item-active' : '' }}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{{ $item['icon'] }}" />
                        </svg>
                        <span>{{ $item['label'] }}</span>
                    </a>
                @endforeach
            </nav>
            <div class="app-sidebar-footer p-4">
                <div class="section-label">Masuk sebagai</div>
                <div class="text-sm font-semibold mt-1">{{ auth()->user()->name ?? 'User' }}</div>
                <div class="text-[11px] text-slate-500">{{ auth()->user()->email ?? '' }}</div>
                <div class="mt-3 flex items-center gap-2 text-[11px]">
                    @if(auth()->user()?->isAdmin())
                        <a href="{{ route('admin.index') }}" class="app-link-info">Admin</a>
                    @endif
                    <form method="POST" action="{{ route('logout') }}" class="inline">
                        @csrf
                        <button type="submit" class="app-link-danger">Logout</button>
                    </form>
                </div>
            </div>
        </aside>

        {{-- Mobile overlay --}}
        <div x-show="sidebarOpen" x-cloak class="app-mobile-overlay fixed inset-0 lg:hidden" x-on:click="sidebarOpen = false"></div>
        <aside x-show="sidebarOpen" x-cloak x-transition
               class="app-sidebar fixed inset-y-0 left-0 w-[200px] lg:hidden z-50">
            <div class="px-4 py-4 flex items-center justify-between border-b border-white/10">
                <div class="flex items-center gap-3">
                    <div class="app-logo-mark h-10 w-10 flex items-center justify-center">
                        SI
                    </div>
                    <div>
                        <div class="app-brand-kicker">Sentimena</div>
                        <div class="app-brand-title">IDX Sentiment</div>
                    </div>
                </div>
                <button x-on:click="sidebarOpen = false" class="text-slate-400 hover:text-slate-100">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <nav class="px-0 py-4 space-y-1 text-sm">
                @foreach($nav as $item)
                    @php $active = request()->routeIs($item['route']); @endphp
                    <a href="{{ $item['href'] }}"
                       class="app-nav-item {{ $active ? 'app-nav-item-active' : '' }}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{{ $item['icon'] }}" />
                        </svg>
                        <span>{{ $item['label'] }}</span>
                    </a>
                @endforeach
            </nav>
        </aside>

        {{-- Content --}}
        <div class="flex-1 lg:ml-[200px] flex flex-col min-h-screen">
            <header class="app-topbar sticky top-0 z-30 px-4 lg:px-6">
                <div class="app-topbar-row flex items-center gap-4">
                    <button class="lg:hidden text-slate-200" x-on:click="sidebarOpen = true">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                    <div class="flex-1 relative" x-data x-on:click.away="$store.stockSearch.results=[]">
                        <div class="app-search px-4">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-5.2-5.2m0 0a7 7 0 1 0-9.9-9.9 7 7 0 0 0 9.9 9.9Z"/>
                            </svg>
                            <input type="text" x-model="$store.stockSearch.query" x-on:input.debounce.300ms="$store.stockSearch.search()" placeholder="Cari kode/nama saham IDX..."
                                   class="app-search-input focus:outline-none px-3 flex-1">
                            <div x-show="$store.stockSearch.loading" class="topbar-loading">Loading...</div>
                        </div>
                        <div x-show="$store.stockSearch.results.length" class="app-search-results absolute mt-2 w-full overflow-hidden">
                            <template x-for="item in $store.stockSearch.results" :key="item.id">
                                <a :href="`/stocks/${item.code}`" class="app-search-result block px-4 py-2">
                                    <div class="flex items-center justify-between">
                                        <div>
                                            <div class="font-semibold" x-text="item.code"></div>
                                            <div class="text-[11px] text-slate-400" x-text="item.company_name"></div>
                                        </div>
                                        <span class="text-[11px] text-slate-500" x-text="item.sector ?? ''"></span>
                                    </div>
                                </a>
                            </template>
                        </div>
                    </div>
                    <div class="hidden md:flex items-center gap-3 text-[11px]" x-data="marketClock()" x-init="start()">
                        <div class="topbar-chip">
                            Market: <span class="font-semibold" :class="statusClass" x-text="statusLabel"></span>
                        </div>
                        <div class="topbar-chip topbar-chip-mono" x-text="timeText + ' WIB'"></div>
                    </div>
                    <div class="relative" x-data="{ open: false }">
                        <button class="app-user-trigger flex items-center gap-3 focus:outline-none" x-on:click="open = !open">
                            <div class="text-right text-sm">
                                <div class="font-semibold">{{ auth()->user()->name ?? 'User' }}</div>
                                <div class="text-[11px] text-slate-500">{{ auth()->user()->email ?? '' }}</div>
                            </div>
                            <div class="app-avatar h-10 w-10 rounded-full flex items-center justify-center uppercase">
                                {{ strtoupper(substr(auth()->user()->name ?? 'U', 0, 2)) }}
                            </div>
                        </button>
                        <div x-show="open" x-cloak x-transition
                             class="app-user-menu absolute right-0 mt-2 w-48 overflow-hidden">
                            <a href="{{ route('profile.edit') }}" class="block px-4 py-2 text-sm">Profil</a>
                            <form method="POST" action="{{ route('logout') }}">
                                @csrf
                                <button type="submit" class="w-full text-left px-4 py-2 text-sm">Logout</button>
                            </form>
                        </div>
                    </div>
                </div>
            </header>

            <div class="ticker-strip w-full sticky top-[52px] z-20">
                <iframe
                    scrolling="no"
                    allowtransparency="true"
                    frameborder="0"
                    src="https://www.tradingview-widget.com/embed-widget/ticker-tape/?locale=en#%7B%22symbols%22%3A%5B%7B%22proName%22%3A%22IDX%3ABBCA%22%2C%22title%22%3A%22BBCA%22%7D%2C%7B%22proName%22%3A%22IDX%3ABBRI%22%2C%22title%22%3A%22BBRI%22%7D%2C%7B%22proName%22%3A%22IDX%3ABMRI%22%2C%22title%22%3A%22BMRI%22%7D%2C%7B%22proName%22%3A%22IDX%3ATLKM%22%2C%22title%22%3A%22TLKM%22%7D%2C%7B%22proName%22%3A%22IDX%3AASII%22%2C%22title%22%3A%22ASII%22%7D%2C%7B%22proName%22%3A%22IDX%3AGOTO%22%2C%22title%22%3A%22GOTO%22%7D%2C%7B%22proName%22%3A%22IDX%3AADRO%22%2C%22title%22%3A%22ADRO%22%7D%2C%7B%22proName%22%3A%22IDX%3AUNVR%22%2C%22title%22%3A%22UNVR%22%7D%2C%7B%22proName%22%3A%22IDX%3AINDF%22%2C%22title%22%3A%22INDF%22%7D%2C%7B%22proName%22%3A%22IDX%3AICBP%22%2C%22title%22%3A%22ICBP%22%7D%2C%7B%22proName%22%3A%22IDX%3ABUMI%22%2C%22title%22%3A%22BUMI%22%7D%2C%7B%22proName%22%3A%22IDX%3ADEWA%22%2C%22title%22%3A%22DEWA%22%7D%2C%7B%22proName%22%3A%22IDX%3ACOMPOSITE%22%2C%22title%22%3A%22IHSG%22%7D%2C%7B%22proName%22%3A%22FOREXCOM%3AUSDIDR%22%2C%22title%22%3A%22USD%2FIDR%22%7D%5D%2C%22colorTheme%22%3A%22dark%22%2C%22isTransparent%22%3Atrue%2C%22displayMode%22%3A%22adaptive%22%2C%22width%22%3A%22100%25%22%2C%22height%22%3A44%7D"
                    title="Ticker Tape"
                    style="display:block; height:44px; width:100%;">
                </iframe>
            </div>

            <main class="flex-1">
                <div class="app-main-shell mx-auto px-4 lg:px-8 py-6 pt-4">
                    {{ $slot }}
                </div>
            </main>
        </div>
    </div>
    <script>
        document.addEventListener('alpine:init', () => {
            window.marketClock = function () {
                return {
                    statusLabel: 'CLOSED',
                    statusClass: 'text-slate-400',
                    timeText: '',
                    start() {
                        this.update();
                        setInterval(() => this.update(), 1000);
                    },
                    update() {
                        const nowJkt = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
                        this.timeText = nowJkt.toLocaleString('id-ID', {
                            timeZone: 'Asia/Jakarta',
                            day: '2-digit',
                            month: 'short',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                            hour12: false,
                        });

                        const day = nowJkt.getDay(); // 0 Sunday, 6 Saturday
                        const h = nowJkt.getHours();
                        const m = nowJkt.getMinutes();
                        const openMorning = (h > 9 || (h === 9 && m >= 0)) && (h < 12 || (h === 12 && m === 0));
                        const openAfternoon = (h > 13 || (h === 13 && m >= 30)) && (h < 15 || (h === 15 && m === 0));
                        const onBreak = (h === 12) || (h === 13 && m < 30);

                        if (day === 0 || day === 6) {
                            this.statusLabel = 'CLOSED';
                            this.statusClass = 'text-slate-400';
                        } else if (openMorning || openAfternoon) {
                            this.statusLabel = 'OPEN';
                            this.statusClass = 'text-green-400';
                        } else if (onBreak) {
                            this.statusLabel = 'BREAK';
                            this.statusClass = 'text-amber-400';
                        } else {
                            this.statusLabel = 'CLOSED';
                            this.statusClass = 'text-slate-400';
                        }
                    },
                };
            };
        });
    </script>
    @stack('scripts')
</body>
</html>
