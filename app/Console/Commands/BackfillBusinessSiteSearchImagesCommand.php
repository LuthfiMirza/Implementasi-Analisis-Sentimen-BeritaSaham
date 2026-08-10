<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\News\BusinessSiteSearchFetcher;
use Illuminate\Console\Command;

/**
 * Fase BG/BH: backfill image_url untuk artikel LAMA tanpa gambar, ambil og:image langsung dari
 * halaman artikel aslinya (source_url) -- generik per-provider, bukan cuma business_site_search.
 * Dipakai juga untuk rss_local: RSS feed cuma nyimpan item TERBARU, jadi artikel lama yang sudah
 * hilang dari feed tidak bisa direkonstruksi dari feed lagi -- og:image di halaman artikelnya
 * sendiri (masih ada di source_url yang tersimpan) jadi satu-satunya jalan backfill yang bekerja
 * untuk artikel seumur apapun. Artikel baru dari kedua provider ini sudah otomatis dapat gambar
 * lewat fetch normal (enclosure/media:content utk RSS, og:image utk business_site_search) --
 * command ini cuma untuk yang sudah terlanjur tersimpan tanpa gambar.
 */
class BackfillBusinessSiteSearchImagesCommand extends Command
{
    protected $signature = 'news:backfill-business-site-images
        {--provider=business_site_search : Provider yang mau di-backfill (business_site_search atau rss_local)}
        {--limit=200 : Maksimal artikel diproses per run}';

    protected $description = 'Backfill image_url artikel lama dari og:image halaman artikel aslinya (business_site_search / rss_local)';

    public function handle(BusinessSiteSearchFetcher $fetcher): int
    {
        $provider = (string) $this->option('provider');
        $limit = (int) $this->option('limit');

        $articles = NewsArticle::where('source_provider', $provider)
            ->whereNull('image_url')
            ->whereNotNull('source_url')
            ->limit($limit)
            ->get();

        if ($articles->isEmpty()) {
            $this->info("Tidak ada artikel {$provider} yang perlu di-backfill.");

            return self::SUCCESS;
        }

        $found = 0;
        $notFound = 0;

        foreach ($articles as $article) {
            $imageUrl = $fetcher->fetchOgImage($article->source_url);
            if ($imageUrl) {
                $article->update(['image_url' => $imageUrl]);
                $found++;
                $this->line("OK  #{$article->id}: {$imageUrl}");
            } else {
                $notFound++;
                $this->line("skip #{$article->id}: og:image tidak ditemukan");
            }
        }

        $this->info("Selesai: {$found} dapat gambar, {$notFound} tidak ada og:image (dari ".count($articles)." diproses).");

        return self::SUCCESS;
    }
}
