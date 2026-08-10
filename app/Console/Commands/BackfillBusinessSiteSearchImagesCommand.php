<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Services\News\BusinessSiteSearchFetcher;
use Illuminate\Console\Command;

/**
 * Fase BG: backfill image_url untuk artikel business_site_search LAMA (tersimpan sebelum
 * BusinessSiteSearchFetcher::fetchOgImage() ditambahkan) -- artikel baru sudah otomatis dapat
 * gambar lewat fetch normal, ini cuma untuk yang sudah terlanjur tersimpan tanpa gambar.
 */
class BackfillBusinessSiteSearchImagesCommand extends Command
{
    protected $signature = 'news:backfill-business-site-images {--limit=200 : Maksimal artikel diproses per run}';

    protected $description = 'Backfill image_url artikel business_site_search lama dari og:image halaman artikel aslinya';

    public function handle(BusinessSiteSearchFetcher $fetcher): int
    {
        $limit = (int) $this->option('limit');

        $articles = NewsArticle::where('source_provider', 'business_site_search')
            ->whereNull('image_url')
            ->whereNotNull('source_url')
            ->limit($limit)
            ->get();

        if ($articles->isEmpty()) {
            $this->info('Tidak ada artikel business_site_search yang perlu di-backfill.');

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
