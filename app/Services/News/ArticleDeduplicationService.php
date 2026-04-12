<?php

namespace App\Services\News;

use Carbon\Carbon;
use Illuminate\Support\Str;

class ArticleDeduplicationService
{
    protected array $seen = [];

    public function reset(): void
    {
        $this->seen = [];
    }

    public function shouldSkip(array $article): bool
    {
        $url = $this->normalizeUrl($article['source_url'] ?? null);
        if ($url && $this->checkAndStore("url:{$url}")) {
            return true;
        }

        $canonical = $this->normalizeUrl($article['canonical_url'] ?? null);
        if ($canonical && $this->checkAndStore("canon:{$canonical}")) {
            return true;
        }

        $titleHash = $this->titleHash($article['title'] ?? '');
        $domain = $this->domain($article['source_url'] ?? null);
        $publishedAt = $article['published_at'] ?? null;

        if ($titleHash && $this->checkAndStore("title:{$titleHash}")) {
            return true;
        }

        $windowKey = $this->windowKey($titleHash, $domain, $publishedAt);
        if ($windowKey && $this->checkAndStore("win:{$windowKey}")) {
            return true;
        }

        return false;
    }

    protected function checkAndStore(string $key): bool
    {
        if (isset($this->seen[$key])) {
            return true;
        }
        $this->seen[$key] = true;
        return false;
    }

    protected function normalizeUrl(?string $url): ?string
    {
        if (! $url) {
            return null;
        }
        $url = trim($url);
        if ($url === '') {
            return null;
        }
        // strip utm / query tracking
        $parts = parse_url($url);
        if (! $parts || ! isset($parts['host'])) {
            return null;
        }

        $scheme = $parts['scheme'] ?? 'https';
        $host = strtolower($parts['host']);
        $path = $parts['path'] ?? '';

        return "{$scheme}://{$host}{$path}";
    }

    protected function domain(?string $url): ?string
    {
        if (! $url) {
            return null;
        }
        $host = parse_url($url, PHP_URL_HOST);
        return $host ? strtolower($host) : null;
    }

    protected function titleHash(string $title): ?string
    {
        $norm = Str::of($title)
            ->lower()
            ->replaceMatches('/[^a-z0-9\s]/', ' ')
            ->replaceMatches('/\s+/', ' ')
            ->trim();

        return $norm->isEmpty() ? null : sha1($norm->value());
    }

    protected function windowKey(?string $titleHash, ?string $domain, $publishedAt): ?string
    {
        if (! $titleHash) {
            return null;
        }

        $date = $publishedAt instanceof Carbon
            ? $publishedAt->copy()->startOfDay()->toDateString()
            : (is_string($publishedAt) ? Carbon::parse($publishedAt)->startOfDay()->toDateString() : null);

        if (! $date) {
            return null;
        }

        return implode('|', [$titleHash, $domain ?? 'no-domain', $date]);
    }
}
