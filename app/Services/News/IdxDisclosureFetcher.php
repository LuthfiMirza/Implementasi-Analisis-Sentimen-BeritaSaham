<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class IdxDisclosureFetcher implements NewsFetcherInterface
{
    public function fetchForStock(Stock $stock, int $limit = 10): array
    {
        $calendarUrl = (string) config('news.idx_disclosure.calendar_url', 'https://www.idx.id/en/listed-companies/listed-company-calendar/');
        $timeout = (int) config('news.idx_disclosure.timeout', config('news.rss_timeout', 8));
        $userAgent = (string) config('news.idx_disclosure.user_agent', config('news.rss_user_agent', 'SentimenaBot/1.0 (+https://sentimena.app)'));

        try {
            $response = Http::withHeaders([
                'User-Agent' => $userAgent,
                'Accept' => 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            ])->timeout($timeout)->get($calendarUrl);
        } catch (\Throwable $e) {
            Log::warning('IDX disclosure request failed', ['error' => $e->getMessage()]);
            return [];
        }

        if (! $response->successful()) {
            Log::warning('IDX disclosure response error', ['status' => $response->status()]);
            return [];
        }

        return collect($this->extractEntries($response->body(), $stock, $calendarUrl))
            ->take($limit)
            ->values()
            ->all();
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    protected function extractEntries(string $html, Stock $stock, string $calendarUrl): array
    {
        $text = html_entity_decode(strip_tags($html));
        $lines = collect(preg_split('/\R/u', $text))
            ->map(fn ($line) => trim(preg_replace('/\s+/u', ' ', (string) $line)))
            ->filter()
            ->values();

        $results = [];
        $code = strtoupper($stock->code);
        $knownCodes = $this->knownCodes();

        for ($index = 0; $index < $lines->count(); $index++) {
            if (strtoupper((string) $lines[$index]) !== $code) {
                continue;
            }

            $description = $this->nextDataLine($lines, $index + 1, $knownCodes);
            if ($description === null) {
                continue;
            }

            $location = $this->nextDataLine($lines, $index + 2, $knownCodes, [$description]);
            $results[] = [
                'provider' => 'idx_disclosure',
                'title' => $description,
                'slug' => Str::slug($code.' '.$description).'-'.Str::random(4),
                'source_name' => 'IDX Listed Company Calendar',
                'source_url' => $calendarUrl,
                'published_at' => Carbon::now('Asia/Jakarta'),
                'summary' => $location,
                'content_snippet' => trim($description.' '.($location ?? '')),
                'sentiment_label' => null,
                'sentiment_score' => null,
                'skip_relevance_rescore' => true,
                'issuer_specificity' => 'direct',
                'relevance_score' => 0.72,
                'relevance_band' => 'high',
                'entity_match_score' => 0.82,
                'market_context_score' => 0.88,
                'language_score' => 1.0,
                'final_quality_score' => 0.79,
                'quality_band' => 'high',
                'matched_keywords' => [$stock->code, $stock->company_name],
                'raw_payload' => [
                    'calendar_url' => $calendarUrl,
                    'code' => $code,
                    'description' => $description,
                    'location' => $location,
                ],
            ];
        }

        return collect($results)
            ->unique(fn ($item) => $item['title'].'|'.$item['summary'])
            ->values()
            ->all();
    }

    /**
     * @param array<int, string> $knownCodes
     * @param array<int, string> $skipValues
     */
    protected function nextDataLine($lines, int $start, array $knownCodes, array $skipValues = []): ?string
    {
        for ($cursor = $start; $cursor < $lines->count(); $cursor++) {
            $line = trim((string) $lines[$cursor]);
            if ($line === '' || in_array($line, $skipValues, true)) {
                continue;
            }

            if (in_array(strtoupper($line), $knownCodes, true)) {
                return null;
            }

            if (in_array($line, ['Code', 'Description', 'Location', 'Back to top'], true)) {
                continue;
            }

            if (str_starts_with($line, 'No listed company')) {
                return null;
            }

            return $line;
        }

        return null;
    }

    /**
     * @return array<int, string>
     */
    protected function knownCodes(): array
    {
        return [
            'AALI', 'ACES', 'ADRO', 'AMRT', 'ANTM', 'ARTO', 'ASII', 'AVIA',
            'BBCA', 'BBNI', 'BBRI', 'BMRI', 'BRIS', 'BUMI', 'CMRY', 'CPIN',
            'EXCL', 'GOTO', 'ICBP', 'INCO', 'INDF', 'INKP', 'ISAT', 'ITMG',
            'JPFA', 'KLBF', 'MAPI', 'MDKA', 'MEDC', 'PGEO', 'SIDO', 'SMGR',
            'TBIG', 'TINS', 'TLKM', 'TPIA', 'UNTR', 'UNVR', 'WIKA',
        ];
    }
}
