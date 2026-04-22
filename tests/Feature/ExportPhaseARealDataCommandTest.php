<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\Stock;
use App\Models\StockPrice;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use Tests\TestCase;

class ExportPhaseARealDataCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_export_command_writes_phase_a_csv_dataset_from_stock_prices(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
            'is_active' => true,
        ]);
        $skippedStock = Stock::factory()->create([
            'code' => 'TLKM',
            'company_name' => 'Telkom Indonesia',
            'sector' => 'Telekomunikasi',
            'is_active' => true,
        ]);

        $this->seedStockHistory($stock, 55);
        $this->seedStockHistory($skippedStock, 40);

        $tempRoot = base_path('tests/tmp/'.Str::uuid()->toString());
        $dataDir = $tempRoot.'/data';
        $metadataPath = $dataDir.'/ticker_metadata.csv';

        try {
            $this->artisan('phase-a:export-real-data', [
                '--data-dir' => Str::after($dataDir, base_path().DIRECTORY_SEPARATOR),
                '--metadata-file' => Str::after($metadataPath, base_path().DIRECTORY_SEPARATOR),
                '--min-rows' => 50,
            ])->assertExitCode(0);

            $this->assertFileExists($dataDir.'/BBCA.csv');
            $this->assertFileDoesNotExist($dataDir.'/TLKM.csv');
            $this->assertFileExists($metadataPath);

            $csv = file($dataDir.'/BBCA.csv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $metadata = file($metadataPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

            $this->assertNotFalse($csv);
            $this->assertNotFalse($metadata);
            $this->assertStringStartsWith('date,open,high,low,close,volume', $csv[0]);
            $this->assertCount(56, $csv);
            $this->assertStringContainsString('ticker,sector,category,company_name', $metadata[0]);
            $this->assertStringContainsString('BBCA,perbankan,finance,"Bank Central Asia"', $metadata[1]);
        } finally {
            File::deleteDirectory($tempRoot);
        }
    }

    public function test_export_command_can_append_daily_sentiment_series_for_item7(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
            'is_active' => true,
        ]);

        $this->seedStockHistory($stock, 55);
        NewsArticle::factory()->for($stock)->create([
            'published_at' => Carbon::create(2026, 1, 8, 9),
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.6,
            'relevance_score' => 0.8,
            'source_weight' => 1.1,
            'final_quality_score' => 0.8,
        ]);
        NewsArticle::factory()->for($stock)->create([
            'published_at' => Carbon::create(2026, 1, 9, 9),
            'sentiment_label' => 'negative',
            'sentiment_score' => -0.3,
            'relevance_score' => 0.9,
            'source_weight' => 1.0,
            'final_quality_score' => 0.75,
        ]);

        $tempRoot = base_path('tests/tmp/'.Str::uuid()->toString());
        $dataDir = $tempRoot.'/data';
        $metadataPath = $dataDir.'/ticker_metadata.csv';

        try {
            $this->artisan('phase-a:export-real-data', [
                '--data-dir' => Str::after($dataDir, base_path().DIRECTORY_SEPARATOR),
                '--metadata-file' => Str::after($metadataPath, base_path().DIRECTORY_SEPARATOR),
                '--min-rows' => 50,
                '--include-sentiment-series' => true,
            ])->assertExitCode(0);

            $csv = file($dataDir.'/BBCA.csv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $metadata = file($metadataPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

            $this->assertNotFalse($csv);
            $this->assertNotFalse($metadata);
            $this->assertStringContainsString('sentiment_average_1d', $csv[0]);
            $this->assertStringContainsString('sentiment_weighted_1d', $csv[0]);
            $this->assertStringContainsString('sentiment_news_count_1d', $csv[0]);
            $this->assertStringContainsString('sentiment_unavailable_count_1d', $csv[0]);
            $this->assertSame(
                'date,open,high,low,close,volume,sentiment_average_1d,sentiment_weighted_1d,sentiment_news_count_1d,sentiment_unavailable_count_1d',
                $csv[0]
            );
            $this->assertTrue(collect($csv)->contains(fn ($line) => str_contains($line, '0.6,0.6,1,0')));
            $this->assertTrue(collect($csv)->contains(fn ($line) => str_contains($line, '0,0,0,0')));
            $this->assertStringContainsString('sentiment_series_included', $metadata[0]);
            $this->assertStringContainsString('trade_date_window_prev_trade_exclusive_current_trade_inclusive', $metadata[1]);
            $this->assertStringContainsString(',2,2', $metadata[1]);
        } finally {
            File::deleteDirectory($tempRoot);
        }
    }

    public function test_export_command_excludes_python_unavailable_articles_from_sentiment_series(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
            'is_active' => true,
        ]);

        $this->seedStockHistory($stock, 55);
        NewsArticle::factory()->for($stock)->create([
            'published_at' => Carbon::create(2026, 1, 8, 9),
            'sentiment_label' => 'positive',
            'sentiment_score' => 0.6,
            'sentiment_method' => 'python',
            'relevance_score' => 0.8,
            'source_weight' => 1.1,
            'final_quality_score' => 0.8,
        ]);
        NewsArticle::factory()->for($stock)->create([
            'published_at' => Carbon::create(2026, 1, 9, 9),
            'sentiment_label' => 'neutral',
            'sentiment_score' => 0.0,
            'sentiment_method' => 'python_unavailable',
            'relevance_score' => 0.9,
            'source_weight' => 1.0,
            'final_quality_score' => 0.75,
        ]);

        $tempRoot = base_path('tests/tmp/'.Str::uuid()->toString());
        $dataDir = $tempRoot.'/data';
        $metadataPath = $dataDir.'/ticker_metadata.csv';

        try {
            $this->artisan('phase-a:export-real-data', [
                '--data-dir' => Str::after($dataDir, base_path().DIRECTORY_SEPARATOR),
                '--metadata-file' => Str::after($metadataPath, base_path().DIRECTORY_SEPARATOR),
                '--min-rows' => 50,
                '--include-sentiment-series' => true,
            ])->assertExitCode(0);

            $csv = array_map('str_getcsv', file($dataDir.'/BBCA.csv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
            $this->assertNotFalse($csv);

            $header = $csv[0];
            $jan10 = collect($csv)
                ->skip(1)
                ->first(fn (array $item) => ($item[0] ?? null) === '2026-01-08');
            $jan11 = collect($csv)
                ->skip(1)
                ->first(fn (array $item) => ($item[0] ?? null) === '2026-01-09');
            $indexedJan10 = array_combine($header, $jan10);
            $indexedJan11 = array_combine($header, $jan11);

            $this->assertSame('0.6', $indexedJan10['sentiment_average_1d']);
            $this->assertSame('0.6', $indexedJan10['sentiment_weighted_1d']);
            $this->assertSame('1', $indexedJan10['sentiment_news_count_1d']);
            $this->assertSame('0', $indexedJan10['sentiment_unavailable_count_1d']);

            $this->assertSame('0', $indexedJan11['sentiment_average_1d']);
            $this->assertSame('0', $indexedJan11['sentiment_weighted_1d']);
            $this->assertSame('0', $indexedJan11['sentiment_news_count_1d']);
            $this->assertSame('1', $indexedJan11['sentiment_unavailable_count_1d']);
        } finally {
            File::deleteDirectory($tempRoot);
        }
    }

    public function test_export_command_prefers_non_seed_price_when_same_trade_date_has_duplicates(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'DEWA',
            'company_name' => 'Darma Henwa',
            'sector' => 'Pertambangan',
            'is_active' => true,
        ]);

        $this->seedStockHistory($stock, 55);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 2, 10, 15),
            'interval_type' => '1d',
            'open' => 99,
            'high' => 111,
            'low' => 98,
            'close' => 101,
            'volume' => 120000,
            'source' => 'seed',
        ]);
        StockPrice::create([
            'stock_id' => $stock->id,
            'price_date' => Carbon::create(2026, 2, 10, 0),
            'interval_type' => '1d',
            'open' => 540,
            'high' => 560,
            'low' => 535,
            'close' => 555,
            'volume' => 5000000,
            'source' => null,
        ]);

        $tempRoot = base_path('tests/tmp/'.Str::uuid()->toString());
        $dataDir = $tempRoot.'/data';
        $metadataPath = $dataDir.'/ticker_metadata.csv';

        try {
            $this->artisan('phase-a:export-real-data', [
                '--data-dir' => Str::after($dataDir, base_path().DIRECTORY_SEPARATOR),
                '--metadata-file' => Str::after($metadataPath, base_path().DIRECTORY_SEPARATOR),
                '--min-rows' => 50,
            ])->assertExitCode(0);

            $csv = array_map('str_getcsv', file($dataDir.'/DEWA.csv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
            $this->assertNotFalse($csv);

            $matchingRows = collect($csv)->filter(fn (array $row) => ($row[0] ?? null) === '2026-02-10')->values();
            $this->assertCount(1, $matchingRows);
            $this->assertSame('555', $matchingRows[0][4]);
        } finally {
            File::deleteDirectory($tempRoot);
        }
    }

    public function test_export_command_skips_ticker_when_history_still_contains_mixed_frequency_contamination(): void
    {
        $stock = Stock::factory()->create([
            'code' => 'BBCA',
            'company_name' => 'Bank Central Asia',
            'sector' => 'Perbankan',
            'is_active' => true,
        ]);

        foreach (['2024-01-31', '2024-02-29', '2024-03-31', '2024-04-30', '2025-01-02'] as $index => $date) {
            StockPrice::create([
                'stock_id' => $stock->id,
                'price_date' => $date,
                'interval_type' => '1d',
                'open' => 100 + $index,
                'high' => 105 + $index,
                'low' => 95 + $index,
                'close' => 102 + $index,
                'volume' => 100000 + $index,
                'source' => 'test',
            ]);
        }

        $tempRoot = base_path('tests/tmp/'.Str::uuid()->toString());
        $dataDir = $tempRoot.'/data';
        $metadataPath = $dataDir.'/ticker_metadata.csv';

        try {
            $this->artisan('phase-a:export-real-data', [
                '--data-dir' => Str::after($dataDir, base_path().DIRECTORY_SEPARATOR),
                '--metadata-file' => Str::after($metadataPath, base_path().DIRECTORY_SEPARATOR),
                '--min-rows' => 1,
            ])->assertExitCode(1);

            $this->assertFileDoesNotExist($dataDir.'/BBCA.csv');
            $this->assertFileDoesNotExist($metadataPath);
        } finally {
            File::deleteDirectory($tempRoot);
        }
    }

    protected function seedStockHistory(Stock $stock, int $days): void
    {
        $start = Carbon::create(2026, 1, 1);
        $current = $start->copy();

        for ($index = 0; $index < $days; $index++) {
            while ($current->isWeekend()) {
                $current->addDay();
            }

            $open = 100 + $index;
            StockPrice::create([
                'stock_id' => $stock->id,
                'price_date' => $current->toDateString(),
                'interval_type' => '1d',
                'open' => $open,
                'high' => $open + 5,
                'low' => $open - 5,
                'close' => $open + 2,
                'volume' => 100000 + ($index * 1000),
                'source' => 'test',
            ]);

            $current->addDay();
        }
    }
}
