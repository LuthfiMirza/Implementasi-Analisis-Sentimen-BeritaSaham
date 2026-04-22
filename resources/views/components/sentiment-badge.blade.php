@props(['label' => 'neutral'])

@php
    $config = match($label) {
        'positive' => ['bg' => 'bg-green-500/10', 'border' => 'border-green-500/30', 'text' => 'text-green-400', 'icon' => '▲', 'name' => 'Positif'],
        'negative' => ['bg' => 'bg-rose-500/10',  'border' => 'border-rose-500/30',  'text' => 'text-rose-400',  'icon' => '▼', 'name' => 'Negatif'],
        'unavailable' => ['bg' => 'bg-amber-500/10', 'border' => 'border-amber-500/30', 'text' => 'text-amber-300', 'icon' => '•', 'name' => 'Unavailable'],
        default    => ['bg' => 'bg-slate-800',     'border' => 'border-slate-700',    'text' => 'text-slate-300', 'icon' => '◆', 'name' => 'Netral'],
    };
@endphp

<span {{ $attributes->merge(['class' => 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border '.$config['bg'].' '.$config['border'].' '.$config['text']]) }}>
    {{ $config['icon'] }} {{ $config['name'] }}
</span>
