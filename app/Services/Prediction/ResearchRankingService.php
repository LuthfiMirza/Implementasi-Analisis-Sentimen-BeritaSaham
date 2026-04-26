<?php

namespace App\Services\Prediction;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Http;

class ResearchRankingService
{
    public function __construct(
        protected ResearchPredictionFeatureService $featureService,
        protected ?string $rankingEndpoint = null,
        protected int $timeout = 6,
    ) {
        $this->rankingEndpoint ??= $this->cfg('prediction.ranking_endpoint', env('PYTHON_RANKING_ENDPOINT'));
        $this->timeout = (int) $this->cfg('prediction.timeout', env('PYTHON_PREDICTION_TIMEOUT', 6));
    }

    public function getRanking(array $stockCodes): array
    {
        $codes = collect($stockCodes)
            ->map(fn ($code) => strtoupper(trim((string) $code)))
            ->filter()
            ->unique()
            ->values();

        if ($codes->count() < 2) {
            return $this->unavailable('Minimal dua ticker diperlukan untuk relative technical strength ranking.');
        }

        $stocks = Stock::query()
            ->whereIn('code', $codes->all())
            ->get()
            ->keyBy('code');

        $orderedStocks = $codes
            ->map(fn (string $code) => $stocks->get($code))
            ->filter(fn ($stock) => $stock instanceof Stock)
            ->values();

        if ($orderedStocks->count() < 2) {
            return $this->unavailable('Ticker yang tersedia belum cukup untuk dibandingkan.');
        }

        $referenceDate = $this->resolveCommonReferenceDate($orderedStocks);
        if (! $referenceDate) {
            return $this->unavailable('Tanggal referensi bersama untuk universe ini belum tersedia.');
        }

        $payloadStocks = $orderedStocks->map(function (Stock $stock) use ($referenceDate): array {
            $features = $this->featureService->buildForDate($stock, collect(), $referenceDate);

            return [
                'ticker' => $stock->code,
                'features' => $features,
            ];
        })->values()->all();

        $result = $this->rankViaPython($payloadStocks);
        if (! $result) {
            return $this->unavailable('Endpoint ranking teknikal belum merespons.', $referenceDate);
        }

        $result['reference_date'] = $referenceDate->toDateString();
        $result['available'] = true;

        return $result;
    }

    protected function rankViaPython(array $stocks): ?array
    {
        if (! $this->rankingEndpoint) {
            return null;
        }

        try {
            $response = Http::timeout($this->timeout)->post($this->rankingEndpoint, [
                'stocks' => $stocks,
            ]);

            if (! $response->successful()) {
                return null;
            }

            $data = $response->json();
            if (! $this->isValidRankingResponse($data)) {
                return null;
            }

            return [
                'ranked' => collect($data['ranked'])->map(function (array $row): array {
                    return [
                        'ticker' => strtoupper((string) ($row['ticker'] ?? '')),
                        'rank' => (int) ($row['rank'] ?? 0),
                        'score' => round((float) ($row['score'] ?? 0), 4),
                        'signal' => (string) ($row['signal'] ?? 'neutral'),
                    ];
                })->values()->all(),
                'model_version' => (string) ($data['model_version'] ?? 'v5_ranking'),
                'horizon_days' => (int) ($data['horizon_days'] ?? 5),
                'generated_at' => (string) ($data['generated_at'] ?? now()->toDateString()),
            ];
        } catch (\Throwable $e) {
            return null;
        }
    }

    protected function resolveCommonReferenceDate(Collection $stocks): ?Carbon
    {
        $commonDates = null;

        foreach ($stocks as $stock) {
            $series = $this->featureService->seriesForStock($stock);
            $dates = $series->keys()->values()->all();
            if ($dates === []) {
                return null;
            }

            $commonDates = $commonDates === null
                ? $dates
                : array_values(array_intersect($commonDates, $dates));

            if ($commonDates === []) {
                return null;
            }
        }

        sort($commonDates);
        $latestCommonDate = end($commonDates);

        return $latestCommonDate ? Carbon::parse($latestCommonDate) : null;
    }

    protected function unavailable(string $message, ?Carbon $referenceDate = null): array
    {
        return [
            'available' => false,
            'message' => $message,
            'ranked' => [],
            'model_version' => 'v5_ranking',
            'horizon_days' => 5,
            'generated_at' => now()->toDateString(),
            'reference_date' => $referenceDate?->toDateString(),
        ];
    }

    protected function isValidRankingResponse(?array $data): bool
    {
        if (! is_array($data) || ! isset($data['ranked']) || ! is_array($data['ranked'])) {
            return false;
        }

        return collect($data['ranked'])->every(function ($row): bool {
            return is_array($row)
                && isset($row['ticker'], $row['rank'], $row['score'], $row['signal']);
        });
    }

    protected function cfg(string $key, $default = null)
    {
        return function_exists('config') ? config($key, $default) : $default;
    }
}
