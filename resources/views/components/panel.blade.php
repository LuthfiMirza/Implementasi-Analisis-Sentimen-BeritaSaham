@props(['padding' => 'p-4'])

<div {{ $attributes->merge([
    'class' => "glass-card {$padding}",
]) }}>
    {{ $slot }}
</div>
