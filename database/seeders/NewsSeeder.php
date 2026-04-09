<?php

namespace Database\Seeders;

use App\Models\ArticleEntity;
use App\Models\NewsArticle;
use App\Models\NewsSource;
use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

class NewsSeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
        $sources = [
            ['name' => 'Mock IDX News', 'type' => 'mock', 'base_url' => 'https://mock-news.local'],
            ['name' => 'Demo RSS Finansial', 'type' => 'rss', 'base_url' => 'https://rss.demo.local'],
            ['name' => 'Manual Analyst Desk', 'type' => 'manual', 'base_url' => null],
        ];

        $sourceModels = collect($sources)->mapWithKeys(function ($data) {
            $source = NewsSource::updateOrCreate(
                ['name' => $data['name']],
                [
                    'type' => $data['type'],
                    'base_url' => $data['base_url'],
                    'is_active' => true,
                    'config_json' => ['seeded' => true],
                ]
            );

            return [$data['name'] => $source];
        });

        $articles = [
            ['stock' => 'BBCA', 'title' => 'Laba BCA tumbuh dobel digit, perbankan tetap defensif', 'sentiment_label' => 'positive', 'sentiment_score' => 0.72],
            ['stock' => 'BBRI', 'title' => 'BRI siapkan dividen jumbo, rasio kecukupan modal terjaga', 'sentiment_label' => 'positive', 'sentiment_score' => 0.65],
            ['stock' => 'TLKM', 'title' => 'Telkom fokus fiberisasi, EBITDA masih solid meski persaingan ketat', 'sentiment_label' => 'neutral', 'sentiment_score' => 0.12],
            ['stock' => 'GOTO', 'title' => 'GoTo kurangi rugi, pasar masih menunggu bukti profitabilitas', 'sentiment_label' => 'neutral', 'sentiment_score' => -0.05],
            ['stock' => 'ASII', 'title' => 'Penjualan otomotif menurun, Astra diversifikasi ke energi baru', 'sentiment_label' => 'negative', 'sentiment_score' => -0.44],
            ['stock' => 'BMRI', 'title' => 'Mandiri catatkan pertumbuhan kredit UMKM di awal tahun', 'sentiment_label' => 'positive', 'sentiment_score' => 0.4],
            ['stock' => 'INDF', 'title' => 'Indofood tanggapi kenaikan bahan baku dengan efisiensi biaya', 'sentiment_label' => 'neutral', 'sentiment_score' => 0.05],
            ['stock' => 'ICBP', 'title' => 'ICBP perluas ekspor mie instan, margin terjaga', 'sentiment_label' => 'positive', 'sentiment_score' => 0.31],
            ['stock' => 'ADRO', 'title' => 'Harga batu bara melemah, Adaro fokus pada energi terbarukan', 'sentiment_label' => 'negative', 'sentiment_score' => -0.52],
            ['stock' => 'UNVR', 'title' => 'Unilever tekan biaya pemasaran, volume mulai pulih', 'sentiment_label' => 'positive', 'sentiment_score' => 0.27],
        ];

        foreach ($articles as $index => $data) {
            $stock = Stock::where('code', $data['stock'])->first();
            $publishedAt = Carbon::now()->subDays($index + 1)->setTime(9, 0);
            $slug = Str::slug($data['title']);

            $article = NewsArticle::updateOrCreate(
                ['slug' => $slug],
                [
                    'stock_id' => $stock?->id,
                    'news_source_id' => $sourceModels['Mock IDX News']->id ?? null,
                    'title' => $data['title'],
                    'source_url' => 'https://news.mock/'.$slug,
                    'published_at' => $publishedAt,
                    'summary' => 'Ringkasan singkat mengenai '.$data['title'],
                    'content_snippet' => 'Berita ini membahas '.$data['stock'].' dan sentimen pasar terkini.',
                    'full_text' => 'Konten lengkap dapat diisi dari crawler atau impor manual.',
                    'sentiment_label' => $data['sentiment_label'],
                    'sentiment_score' => $data['sentiment_score'],
                    'language' => 'id',
                    'raw_payload' => ['seeded' => true],
                    'fetched_at' => now(),
                ]
            );

            if ($stock) {
                ArticleEntity::firstOrCreate([
                    'news_article_id' => $article->id,
                    'entity_name' => $stock->company_name,
                    'entity_type' => 'company',
                ]);
            }
        }
    }
}
