<?php

namespace App\Services\Research;

use Illuminate\Support\Facades\File;
use InvalidArgumentException;
use RecursiveDirectoryIterator;
use RecursiveIteratorIterator;
use SplFileInfo;

class ResearchArtifactDiscoveryService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_research');
    }

    public function discover(?string $path = null, ?string $ticker = null, ?string $type = null): array
    {
        $root = $this->normalizeInputPath($path ?? $this->config['allowed_roots'][0]);
        $this->assertAllowedPath($root);

        if (! File::isDirectory($root)) {
            throw new InvalidArgumentException("Research artifact path is not a directory: {$root}");
        }

        $files = [];
        $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, RecursiveDirectoryIterator::SKIP_DOTS));
        foreach ($iterator as $file) {
            if (! $file instanceof SplFileInfo || ! $file->isFile()) {
                continue;
            }
            $candidate = $file->getPathname();
            if ($file->getExtension() !== 'json') {
                continue;
            }
            if (str_starts_with($file->getFilename(), '.')) {
                continue;
            }
            $real = realpath($candidate);
            if ($real === false) {
                continue;
            }
            $this->assertAllowedPath($real);
            if ($file->isLink() && ! $this->isWithinAllowedRoot($real)) {
                throw new InvalidArgumentException("Symlink escapes allowed roots: {$candidate}");
            }
            if ($file->getSize() > (int) $this->config['maximum_file_size']) {
                throw new InvalidArgumentException("Research artifact exceeds maximum file size: {$candidate}");
            }
            if (($ticker || $type) && ! $this->passesRootFilters($real, $ticker, $type)) {
                continue;
            }
            $files[] = $real;
        }

        sort($files, SORT_STRING);
        return $files;
    }

    public function assertAllowedPath(string $path): string
    {
        if (str_contains($path, '..')) {
            throw new InvalidArgumentException('Path traversal is not allowed.');
        }
        $real = realpath($path) ?: realpath(dirname($path));
        if ($real === false || ! $this->isWithinAllowedRoot($real)) {
            throw new InvalidArgumentException("Path is outside allowed research roots: {$path}");
        }
        return $real;
    }

    protected function isWithinAllowedRoot(string $path): bool
    {
        $normalized = rtrim(str_replace('\\', '/', $path), '/');
        foreach ($this->config['allowed_roots'] as $root) {
            $rootReal = realpath($root);
            if ($rootReal === false) {
                continue;
            }
            $allowed = rtrim(str_replace('\\', '/', $rootReal), '/');
            if ($normalized === $allowed || str_starts_with($normalized.'/', $allowed.'/')) {
                return true;
            }
        }
        return false;
    }

    protected function normalizeInputPath(string $path): string
    {
        if (! str_starts_with($path, DIRECTORY_SEPARATOR)) {
            $path = base_path($path);
        }
        return $path;
    }

    protected function passesRootFilters(string $path, ?string $ticker, ?string $type): bool
    {
        $payload = json_decode((string) File::get($path), true, (int) $this->config['maximum_json_depth']);
        if (! is_array($payload)) {
            return false;
        }
        if ($ticker !== null && strtoupper((string) ($payload['ticker'] ?? '')) !== strtoupper($ticker)) {
            return false;
        }
        if ($type !== null && (string) ($payload['artifact_type'] ?? '') !== $type) {
            return false;
        }
        return true;
    }
}
