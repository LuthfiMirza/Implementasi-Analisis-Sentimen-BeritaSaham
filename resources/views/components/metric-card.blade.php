@props([
    'label' => '',
    'value' => '',
    'hint' => '',
    'change' => null,
])

@php
    $changeColor = $change === null ? 'text-slate-400' : ($change >= 0 ? 'text-green-400' : 'text-rose-400');
    $badge = $change === null ? '' : ($change >= 0 ? '+'.number_format($change, 2).'%' : number_format($change, 2).'%');
@endphp

<x-panel padding="p-4" {{ $attributes }}>
    <p class="metric-label">{{ $label }}</p>
    <div class="flex items-baseline justify-between gap-2 mt-1">
        <h3 class="text-2xl font-bold text-slate-100">{{ $value }}</h3>
        @if($change !== null)
            <span class="text-xs font-semibold {{ $changeColor }}">{{ $badge }}</span>
        @endif
    </div>
    @if($hint)
        <p class="text-xs text-slate-400 mt-1">{{ $hint }}</p>
    @endif
</x-panel>
