<?php

namespace Tests\Feature;

use App\Models\Stock;
use App\Services\Prediction\ResearchPredictionFeatureService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class ResearchPredictionFeatureServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_live_features_compute_return_5d_cross_section_rank_from_stock_csvs(): void
    {
        $dir = storage_path('framework/testing/stock-csv-'.uniqid());
        File::ensureDirectoryExists($dir);

        $this->writePrices($dir.'/AAA.csv', [100, 100, 100, 100, 100, 110]);
        $this->writePrices($dir.'/BBB.csv', [100, 100, 100, 100, 100, 100]);
        $this->writePrices($dir.'/CCC.csv', [100, 100, 100, 100, 100, 90]);

        $stock = Stock::factory()->create(['code' => 'AAA']);
        $features = (new ResearchPredictionFeatureService($dir, $dir.'/missing-ihsg.csv'))
            ->buildForDate($stock, collect(), '2026-01-06');

        $this->assertSame(1.0, $features['return_5d_cross_section_rank']);
        $this->assertSame(0.10, $features['return_5d']);

        File::deleteDirectory($dir);
    }

    private function writePrices(string $path, array $closes): void
    {
        $handle = fopen($path, 'wb');
        fputcsv($handle, ['date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']);
        foreach ($closes as $index => $close) {
            fputcsv($handle, [
                '2026-01-0'.($index + 1),
                $close,
                $close,
                $close,
                $close,
                $close,
                1000,
            ]);
        }
        fclose($handle);
    }
}
