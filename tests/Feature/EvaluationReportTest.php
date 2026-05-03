<?php

namespace Tests\Feature;

use App\Services\Analytics\EvaluationReportService;
use App\Models\Stock;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class EvaluationReportTest extends TestCase
{
    public function test_evaluate_report_artisan_command_outputs_valid_json_structure(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->app->instance(EvaluationReportService::class, new class extends EvaluationReportService {
            public function __construct() {}
            public function generate(Stock $stock, int $period = 30, bool $includeMacroNews = true, ?bool $macroRegulatorySignal = null): array
            {
                return [
                    'correlation' => ['same_day' => 0.1],
                    'sentiment_distribution' => ['positive' => 1, 'neutral' => 0, 'negative' => 0],
                    'price_trend' => 'naik',
                ];
            }
        });

        // Report JSON is used as an external thesis evaluation artifact.
        $exitCode = Artisan::call('evaluate:report', ['code' => $stock->code, '--period' => 30]);
        $output = Artisan::output();

        $this->assertSame(0, $exitCode);
        $this->assertStringContainsString('"correlation"', $output);
        $this->assertStringContainsString('"sentiment_distribution"', $output);
        $this->assertStringContainsString('"price_trend"', $output);
    }
}
