@props(['label' => 'neutral'])

@php
    $classes = [
        'positive' => 'bg-green-500/15 text-green-300 border border-green-500/30',
        'negative' => 'bg-rose-500/15 text-rose-300 border border-rose-500/30',
        'neutral' => 'bg-amber-500/10 text-amber-200 border border-amber-500/30',
    ];
@endphp

<span {{ $attributes->merge(['class' => 'text-[11px] px-2 py-1 rounded-full '.$classes[$label] ?? $classes['neutral']]) }}>
    {{ ucfirst($label) }}
</span>
