<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Str;

class RssNewsFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 5): array
    {
        $results = [];

        for ($i = 0; $i < $limit; $i++) {
            $title = sprintf('RSS highlight %s #%d', $stock->code, $i + 1);
            $slug = Str::slug($title);

            $results[] = [
                'title' => $title,
                'slug' => $slug,
                'source_name' => 'RSS Demo',
                'source_url' => 'https://rss.demo.local/'.$slug,
                'published_at' => Carbon::now()->subDays($i + 1),
                'summary' => 'Contoh berita dari RSS '.$stock->code,
                'content_snippet' => 'Berita ini hanya contoh RSS, implementasi fetcher dapat diganti provider asli.',
                'sentiment_label' => 'neutral',
                'sentiment_score' => 0.0,
                'raw_payload' => ['rss' => true],
            ];
        }

        return $results;
    }
}
