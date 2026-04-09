<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">

    <title>{{ config('app.name', 'Sentimena') }}</title>

    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="bg-slate-950 text-slate-100" x-data="{ sidebarOpen: false }">
    <div class="min-h-screen flex">
        {{-- Sidebar --}}
        <aside class="hidden lg:flex lg:flex-col w-64 border-r border-slate-800 bg-slate-900/80 backdrop-blur fixed inset-y-0">
            <div class="px-6 py-5 flex items-center gap-3 border-b border-slate-800">
                <div class="h-10 w-10 rounded-xl bg-gradient-to-br from-sky-500 to-cyan-400 flex items-center justify-center text-slate-900 font-black tracking-tight">
                    SI
                </div>
                <div>
                    <div class="text-xs uppercase text-slate-400">Sentimena</div>
                    <div class="font-semibold text-slate-50">IDX Sentiment</div>
                </div>
            </div>
            <nav class="flex-1 px-3 py-4 space-y-1 text-sm">
                @php
                    $nav = [
                        ['label' => 'Dashboard', 'route' => 'dashboard', 'href' => route('dashboard'), 'icon' => 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001 1h4a1 1 0 001-1m-6 0V9m0 12h6'],
                        ['label' => 'Berita Terkini', 'route' => 'news.index', 'href' => route('news.index'), 'icon' => 'M4 6h16M4 10h16M4 14h10m-4 4h4'],
                        ['label' => 'Watchlist', 'route' => 'watchlist.index', 'href' => route('watchlist.index'), 'icon' => 'M5 4h14a1 1 0 011 1v10a1 1 0 01-.553.894l-6.894 3.447a1 1 0 01-.894 0L4.765 15.96A1 1 0 014 15V5a1 1 0 011-1z'],
                        ['label' => 'Prediksi', 'route' => 'analytics.index', 'href' => route('analytics.index'), 'icon' => 'M3 17l6-6 4 4 8-8'],
                    ];
                @endphp
                @foreach($nav as $item)
                    @php $active = request()->routeIs($item['route']); @endphp
                    <a href="{{ $item['href'] }}"
                       class="flex items-center gap-3 px-3 py-2 rounded-lg border {{ $active ? 'border-sky-500/60 bg-sky-500/10 text-sky-100' : 'border-transparent text-slate-300 hover:border-slate-800 hover:bg-slate-900/80' }}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{{ $item['icon'] }}" />
                        </svg>
                        <span>{{ $item['label'] }}</span>
                    </a>
                @endforeach
            </nav>
            <div class="p-4 border-t border-slate-800">
                <div class="text-xs text-slate-500">Masuk sebagai</div>
                <div class="text-sm font-semibold">{{ auth()->user()->name ?? 'User' }}</div>
                <div class="text-xs text-slate-500">{{ auth()->user()->email ?? '' }}</div>
                <div class="mt-3 flex items-center gap-2 text-xs">
                    @if(auth()->user()?->isAdmin())
                        <a href="{{ route('admin.index') }}" class="text-sky-400 hover:text-sky-300">Admin</a>
                    @endif
                    <form method="POST" action="{{ route('logout') }}" class="inline">
                        @csrf
                        <button type="submit" class="text-rose-400 hover:text-rose-300">Logout</button>
                    </form>
                </div>
            </div>
        </aside>

        {{-- Mobile overlay --}}
        <div x-show="sidebarOpen" x-cloak class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm lg:hidden" x-on:click="sidebarOpen = false"></div>
        <aside x-show="sidebarOpen" x-cloak x-transition
               class="fixed inset-y-0 left-0 w-64 bg-slate-900 border-r border-slate-800 lg:hidden z-50">
            <div class="px-6 py-5 flex items-center justify-between border-b border-slate-800">
                <div class="flex items-center gap-3">
                    <div class="h-10 w-10 rounded-xl bg-gradient-to-br from-sky-500 to-cyan-400 flex items-center justify-center text-slate-900 font-black tracking-tight">
                        SI
                    </div>
                    <div>
                        <div class="text-xs uppercase text-slate-400">Sentimena</div>
                        <div class="font-semibold text-slate-50">IDX Sentiment</div>
                    </div>
                </div>
                <button x-on:click="sidebarOpen = false" class="text-slate-400 hover:text-slate-200">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <nav class="px-3 py-4 space-y-1 text-sm">
                @foreach($nav as $item)
                    @php $active = request()->routeIs($item['route']); @endphp
                    <a href="{{ $item['href'] }}"
                       class="flex items-center gap-3 px-3 py-2 rounded-lg border {{ $active ? 'border-sky-500/60 bg-sky-500/10 text-sky-100' : 'border-transparent text-slate-300 hover:border-slate-800 hover:bg-slate-900/80' }}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{{ $item['icon'] }}" />
                        </svg>
                        <span>{{ $item['label'] }}</span>
                    </a>
                @endforeach
            </nav>
        </aside>

        {{-- Content --}}
        <div class="flex-1 lg:ml-64 flex flex-col min-h-screen">
            <header class="sticky top-0 z-30 border-b border-slate-800/70 bg-slate-900/80 backdrop-blur px-4 lg:px-6 py-4">
                <div class="flex items-center gap-4">
                    <button class="lg:hidden text-slate-200" x-on:click="sidebarOpen = true">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                    <div class="flex-1 relative" x-data x-on:click.away="$store.stockSearch.results=[]">
                        <div class="flex items-center gap-2 bg-slate-900/60 border border-slate-800/70 rounded-2xl px-4 py-2.5 shadow-lg shadow-sky-500/5 backdrop-blur focus-within:ring-2 focus-within:ring-sky-500/40">
                            <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-5.2-5.2m0 0a7 7 0 1 0-9.9-9.9 7 7 0 0 0 9.9 9.9Z"/>
                            </svg>
                            <input type="text" x-model="$store.stockSearch.query" x-on:input.debounce.300ms="$store.stockSearch.search()" placeholder="Cari kode/nama saham IDX..."
                                   class="bg-transparent focus:outline-none text-sm px-3 flex-1 placeholder-slate-500 focus:placeholder-slate-400">
                            <div x-show="$store.stockSearch.loading" class="text-xs text-sky-400">Loading...</div>
                        </div>
                        <div x-show="$store.stockSearch.results.length" class="absolute mt-2 w-full bg-slate-900 border border-slate-800 rounded-xl shadow-xl overflow-hidden">
                            <template x-for="item in $store.stockSearch.results" :key="item.id">
                                <a :href="`/stocks/${item.code}`" class="block px-4 py-2 hover:bg-slate-800">
                                    <div class="flex items-center justify-between">
                                        <div>
                                            <div class="font-semibold" x-text="item.code"></div>
                                            <div class="text-xs text-slate-400" x-text="item.company_name"></div>
                                        </div>
                                        <span class="text-xs text-slate-500" x-text="item.sector ?? ''"></span>
                                    </div>
                                </a>
                            </template>
                        </div>
                    </div>
                    <div class="hidden md:flex items-center gap-3 text-xs">
                        <div class="px-3 py-2 rounded-lg border border-slate-800 bg-slate-900/70">
                            Market: <span class="text-green-400 font-semibold">OPEN</span>
                        </div>
                        <div class="px-3 py-2 rounded-lg border border-slate-800 bg-slate-900/70">
                            {{ now()->setTimezone('Asia/Jakarta')->format('d M Y, H:i') }} WIB
                        </div>
                    </div>
                    <div class="relative" x-data="{ open: false }">
                        <button class="flex items-center gap-3 focus:outline-none" x-on:click="open = !open">
                            <div class="text-right text-sm">
                                <div class="font-semibold">{{ auth()->user()->name ?? 'User' }}</div>
                                <div class="text-slate-400">{{ auth()->user()->email ?? '' }}</div>
                            </div>
                            <div class="h-10 w-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs uppercase">
                                {{ strtoupper(substr(auth()->user()->name ?? 'U', 0, 2)) }}
                            </div>
                        </button>
                        <div x-show="open" x-cloak x-transition
                             class="absolute right-0 mt-2 w-48 rounded-xl border border-slate-800 bg-slate-900 shadow-xl overflow-hidden">
                            <a href="{{ route('profile.edit') }}" class="block px-4 py-2 text-sm hover:bg-slate-800">Profil</a>
                            <form method="POST" action="{{ route('logout') }}">
                                @csrf
                                <button type="submit" class="w-full text-left px-4 py-2 text-sm hover:bg-slate-800">Logout</button>
                            </form>
                        </div>
                    </div>
                </div>
            </header>

            <main class="flex-1">
                <div class="max-w-[1400px] mx-auto px-4 lg:px-8 py-6">
                    {{ $slot }}
                </div>
            </main>
        </div>
    </div>
    @stack('scripts')
</body>
</html>
