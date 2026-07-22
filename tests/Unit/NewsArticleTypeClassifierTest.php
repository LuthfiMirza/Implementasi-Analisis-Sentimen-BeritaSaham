<?php

namespace Tests\Unit;

use App\Models\NewsArticle;
use App\Services\Sentiment\NewsArticleTypeClassifier;
use PHPUnit\Framework\TestCase;

class NewsArticleTypeClassifierTest extends TestCase
{
    public function test_classifies_macro_multi_issuer_recommendation_and_specific_articles(): void
    {
        $classifier = new NewsArticleTypeClassifier();

        $macro = new NewsArticle(['stock_id' => null, 'title' => 'IHSG Menguat Setelah BI Tahan Suku Bunga']);
        $multi = new NewsArticle(['stock_id' => 1, 'title' => 'Rekomendasi Saham BBCA dan BBRI Hari Ini']);
        $specific = new NewsArticle(['stock_id' => 1, 'title' => 'BBCA Cetak Laba Bersih Naik']);

        $this->assertSame('macro', $classifier->classify($macro));
        $this->assertSame('multi_emiten_recommendation', $classifier->classify($multi));
        $this->assertSame('emiten_spesifik', $classifier->classify($specific));
    }
}
