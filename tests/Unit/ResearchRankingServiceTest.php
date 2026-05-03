<?php

namespace Tests\Unit;

use App\Models\Stock;
use App\Services\Prediction\ResearchPredictionFeatureService;
use App\Services\Prediction\ResearchRankingService;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ResearchRankingServiceTest extends TestCase
{
    public function test_research_ranking_service_sends_correct_payload_to_rank_stocks_endpoint(): void
    {
        Config::set('prediction.ranking_endpoint', 'https://python.test/rank-stocks');
        $bbca = $this->seedStock('BBCA');
        $bbri = $this->seedStock('BBRI');
        Http::fake(['python.test/*' => Http::response([
            'ranked' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.88, 'signal' => 'strong_candidate'],
                ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.72, 'signal' => 'candidate'],
            ],
            'model_version' => 'test-v1',
            'horizon_days' => 5,
        ])]);

        $result = (new ResearchRankingService($this->featureService()))->getRanking([$bbca->code, $bbri->code]);

        // Payload must contain ticker-feature pairs expected by FastAPI.
        Http::assertSent(fn ($request) => $request->url() === 'https://python.test/rank-stocks'
            && isset($request['stocks'][0]['ticker'], $request['stocks'][0]['features']));
        $this->assertTrue($result['available']);
    }

    public function test_unavailable_python_endpoint_returns_unavailable_status_without_fake_ranking(): void
    {
        Config::set('prediction.ranking_endpoint', 'https://python.test/rank-stocks');
        $this->seedStock('BBCA');
        $this->seedStock('BBRI');
        Http::fake(['python.test/*' => Http::response(null, 503)]);

        $result = (new ResearchRankingService($this->featureService()))->getRanking(['BBCA', 'BBRI']);

        // Ranking must not fabricate candidates when ML service is down.
        $this->assertFalse($result['available']);
        $this->assertSame([], $result['ranked']);
    }

    public function test_ranking_response_contract_and_sort_order(): void
    {
        Config::set('prediction.ranking_endpoint', 'https://python.test/rank-stocks');
        $this->seedStock('BBCA');
        $this->seedStock('BBRI');
        Http::fake(['python.test/*' => Http::response([
            'ranked' => [
                ['ticker' => 'BBCA', 'rank' => 1, 'score' => 0.9, 'signal' => 'strong_candidate'],
                ['ticker' => 'BBRI', 'rank' => 2, 'score' => 0.4, 'signal' => 'neutral'],
            ],
            'model_version' => 'test-v1',
            'horizon_days' => 5,
        ])]);

        $result = (new ResearchRankingService($this->featureService()))->getRanking(['BBCA', 'BBRI']);

        // UI ranking rows rely on complete normalized stock ranking fields.
        foreach ($result['ranked'] as $row) {
            $this->assertArrayHasKey('ticker', $row);
            $this->assertArrayHasKey('rank', $row);
            $this->assertArrayHasKey('score', $row);
            $this->assertArrayHasKey('signal', $row);
            $this->assertContains($row['signal'], ['strong_candidate', 'candidate', 'neutral', 'avoid']);
            $this->assertGreaterThanOrEqual(0, $row['score']);
            $this->assertLessThanOrEqual(1, $row['score']);
        }
        $this->assertGreaterThanOrEqual($result['ranked'][1]['score'], $result['ranked'][0]['score']);
    }

    private function featureService(): ResearchPredictionFeatureService
    {
        return new class extends ResearchPredictionFeatureService {
            public function seriesForStock(Stock $stock): Collection
            {
                return collect(['2026-04-30' => ['return_5d' => 0.02]]);
            }
            public function buildForDate(Stock $stock, Collection $articles, $referenceDate, int $sentimentLookbackDays = 5): array
            {
                return ['return_5d' => 0.02, 'volume_ratio_5d' => 1.1, 'reference_date' => '2026-04-30'];
            }
        };
    }
}
