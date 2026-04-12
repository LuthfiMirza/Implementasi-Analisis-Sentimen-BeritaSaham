<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\NewsApiFetcher;
use App\Services\News\StockKeywordMapper;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class NewsApiQueryLengthTest extends TestCase
{
    use RefreshDatabase;

    public function test_query_is_truncated_below_limit(): void
    {
        $stock = Stock::factory()->create(['code' => 'LONG', 'company_name' => 'Perusahaan Nama Sangat Panjang Sekali untuk Uji']);

        $mapper = new class extends StockKeywordMapper {
            public function contextualQuery(\App\Models\Stock $stock, ?array $context = null): string
            {
                return str_repeat('"kata" OR ', 120); // panjang > 480
            }

            public function queryString(\App\Models\Stock $stock): string
            {
                return str_repeat('"alias" OR ', 120);
            }
        };

        Http::fake([
            '*' => Http::response(['status' => 'ok', 'totalResults' => 0, 'articles' => []], 200),
        ]);

        $fetcher = new NewsApiFetcher($mapper);
        $fetcher->fetchForStock($stock, 5);

        Http::assertSent(function ($request) {
            $q = $request->data()['q'] ?? '';
            return strlen($q) <= 480;
        });
    }
}
