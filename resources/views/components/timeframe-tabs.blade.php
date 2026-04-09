@props([
    'active' => '1d',
    'intervals' => ['1d' => '1D', '1w' => '1W', '1m' => '1M', '3m' => '3M'],
    'code' => null,
    'routeName' => 'dashboard',
])

<div {{ $attributes->merge(['class' => 'flex items-center gap-2']) }}>
    @foreach($intervals as $key => $label)
        <a href="{{ route($routeName, ['code' => $code, 'interval' => $key]) }}"
           class="px-3 py-1.5 rounded-full border text-xs {{ $active === $key ? 'border-sky-400 bg-sky-500/15 text-sky-200' : 'border-slate-700 text-slate-400 hover:border-slate-500' }}">
            {{ $label }}
        </a>
    @endforeach
</div>
