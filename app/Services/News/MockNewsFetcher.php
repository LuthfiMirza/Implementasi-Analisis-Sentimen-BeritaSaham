<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Str;

class MockNewsFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $sentiments = [
            ['label' => 'positive', 'score' => 0.6],
            ['label' => 'neutral', 'score' => 0.0],
            ['label' => 'negative', 'score' => -0.5],
        ];

        $results = [];
        for ($i = 0; $i < $limit; $i++) {
            $sentiment = $sentiments[$i % count($sentiments)];
            $title = sprintf('%s: %s berita ke-%d', $stock->code, $this->headlinePrefix($sentiment['label']), $i + 1);
            $slug = Str::slug($title);

            $results[] = [
                'title' => $title,
                'slug' => $slug,
                'source_name' => 'Mock Provider',
                'source_url' => 'https://mock-news.local/'.$slug,
                'published_at' => Carbon::now()->subHours($i + 1),
                'summary' => 'Berita mock untuk demonstrasi dashboard sentimen saham '.$stock->code,
                'content_snippet' => 'Konten ini dihasilkan sebagai data dummy untuk demo skripsi.',
                'sentiment_label' => $sentiment['label'],
                'sentiment_score' => $sentiment['score'],
                'raw_payload' => ['mock' => true],
            ];
        }

        return $results;
    }

    protected function headlinePrefix(string $label): string
    {
        return match ($label) {
            'positive' => 'Sentimen positif',
            'negative' => 'Sentimen negatif',
            default => 'Sentimen netral',
        };
    }
}
