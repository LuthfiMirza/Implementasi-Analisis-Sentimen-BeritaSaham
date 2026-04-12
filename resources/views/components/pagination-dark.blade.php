@if ($paginator->hasPages())
    <nav role="navigation" aria-label="Pagination Navigation" class="flex items-center space-x-1 text-sm">
        {{-- Previous Page Link --}}
        @if ($paginator->onFirstPage())
            <span class="px-2.5 py-1.5 rounded-lg bg-slate-800 text-slate-500 border border-slate-800 cursor-not-allowed select-none">
                ‹
            </span>
        @else
            <a class="px-2.5 py-1.5 rounded-lg bg-slate-900 text-slate-100 border border-slate-700 hover:border-slate-500 transition"
               href="{{ $paginator->previousPageUrl() }}" rel="prev">
                ‹
            </a>
        @endif

        {{-- Pagination Elements --}}
        @foreach ($elements as $element)
            {{-- "Three Dots" Separator --}}
            @if (is_string($element))
                <span class="px-2 py-1 text-slate-500">{{ $element }}</span>
            @endif

            {{-- Array Of Links --}}
            @if (is_array($element))
                @foreach ($element as $page => $url)
                    @if ($page == $paginator->currentPage())
                        <span class="px-3 py-1.5 rounded-lg bg-sky-500 text-slate-900 border border-sky-400 font-semibold">{{ $page }}</span>
                    @else
                        <a class="px-3 py-1.5 rounded-lg bg-slate-900 text-slate-100 border border-slate-700 hover:border-slate-500 transition"
                           href="{{ $url }}">
                            {{ $page }}
                        </a>
                    @endif
                @endforeach
            @endif
        @endforeach

        {{-- Next Page Link --}}
        @if ($paginator->hasMorePages())
            <a class="px-2.5 py-1.5 rounded-lg bg-slate-900 text-slate-100 border border-slate-700 hover:border-slate-500 transition"
               href="{{ $paginator->nextPageUrl() }}" rel="next">
                ›
            </a>
        @else
            <span class="px-2.5 py-1.5 rounded-lg bg-slate-800 text-slate-500 border border-slate-800 cursor-not-allowed select-none">
                ›
            </span>
        @endif
    </nav>
@endif
