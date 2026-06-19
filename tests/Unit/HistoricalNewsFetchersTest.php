<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\News\FinnhubNewsFetcher;
use App\Services\News\GdeltFetcher;
use App\Services\News\GNewsFetcher;
use App\Services\News\NewsApiFetcher;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class HistoricalNewsFetchersTest extends TestCase
{
    use RefreshDatabase;

    public function test_gdelt_historical_sends_datetime_range(): void
    {
        Http::fake([
            'api.gdeltproject.org/*' => Http::response([
                'articles' => [[
                    'title' => 'BBCA historical news',
                    'url' => 'https://example.com/gdelt',
                    'seendate' => '20251001120000',
                    'sourceCommonName' => 'Example',
                ]],
            ]),
        ]);

        $articles = (new GdeltFetcher())->fetchHistorical('BBCA', Carbon::parse('2025-10-01'), Carbon::parse('2025-10-31'), 300);

        $this->assertCount(1, $articles);
        Http::assertSent(fn ($request) => $request['startdatetime'] === '20250930170000'
            && $request['enddatetime'] === '20251030170000'
            && $request['maxrecords'] === 250);
    }

    public function test_newsapi_historical_paginates_everything_endpoint(): void
    {
        config()->set('services.news.api_base_url', 'https://newsapi.org/v2/everything');
        config()->set('services.news.api_key', 'demo-key');
        Http::fakeSequence('newsapi.org/*')
            ->push(['totalResults' => 2, 'articles' => [[
                'title' => 'BBCA page 1',
                'url' => 'https://example.com/1',
                'publishedAt' => '2025-10-01T00:00:00Z',
                'source' => ['name' => 'Example'],
            ]]])
            ->push(['totalResults' => 2, 'articles' => [[
                'title' => 'BBCA page 2',
                'url' => 'https://example.com/2',
                'publishedAt' => '2025-10-02T00:00:00Z',
                'source' => ['name' => 'Example'],
            ]]]);

        $stock = Stock::factory()->create(['code' => 'BBCA', 'company_name' => 'Bank Central Asia']);
        $articles = (new NewsApiFetcher())->fetchHistorical($stock, Carbon::parse('2025-10-01'), Carbon::parse('2025-10-31'), 2);

        $this->assertCount(2, $articles);
        Http::assertSent(fn ($request) => str_starts_with($request['from'], '2025-10-01T00:00:00')
            && str_starts_with($request['to'], '2025-10-31T00:00:00')
            && $request['page'] === 1);
    }

    public function test_gnews_historical_sends_from_to(): void
    {
        config()->set('services.gnews.api_base_url', 'https://gnews.io/api/v4/search');
        config()->set('services.gnews.api_key', 'demo-key');
        Http::fake([
            'gnews.io/*' => Http::response(['articles' => [[
                'title' => 'TLKM historical',
                'url' => 'https://example.com/gnews',
                'publishedAt' => '2025-11-01T00:00:00Z',
                'source' => ['name' => 'GNews'],
            ]]]),
        ]);

        $stock = Stock::factory()->create(['code' => 'TLKM', 'company_name' => 'Telkom Indonesia']);
        $articles = (new GNewsFetcher())->fetchHistorical($stock, Carbon::parse('2025-11-01'), Carbon::parse('2025-11-30'), 10);

        $this->assertNotEmpty($articles);
        Http::assertSent(fn ($request) => str_starts_with($request['from'], '2025-11-01T00:00:00')
            && str_starts_with($request['to'], '2025-11-30T00:00:00'));
    }

    public function test_finnhub_historical_chunks_monthly(): void
    {
        config()->set('services.finnhub.api_key', 'demo-key');
        config()->set('services.finnhub.news_base_url', 'https://finnhub.io/api/v1/company-news');
        Http::fake([
            'finnhub.io/*' => Http::response([[
                'headline' => 'BBRI historical',
                'url' => 'https://example.com/finnhub',
                'datetime' => Carbon::parse('2025-10-15')->timestamp,
                'source' => 'Finnhub',
            ]]),
        ]);

        $articles = (new FinnhubNewsFetcher())->fetchHistorical('BBRI', Carbon::parse('2025-10-15'), Carbon::parse('2025-11-05'), 10);

        $this->assertNotEmpty($articles);
        Http::assertSent(fn ($request) => $request['symbol'] === 'BBRI.JK' && $request['from'] === '2025-10-15' && $request['to'] === '2025-10-31');
        Http::assertSent(fn ($request) => $request['symbol'] === 'BBRI.JK' && $request['from'] === '2025-11-01' && $request['to'] === '2025-11-05');
    }
}
