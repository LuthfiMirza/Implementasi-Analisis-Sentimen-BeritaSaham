@props(['padding' => 'p-4'])

<div {{ $attributes->merge([
    'class' => "glass-card border border-slate-800/80 rounded-2xl {$padding}",
]) }}>
    {{ $slot }}
</div>
