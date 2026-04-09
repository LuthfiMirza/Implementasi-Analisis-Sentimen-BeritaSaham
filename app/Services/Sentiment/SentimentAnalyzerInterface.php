<?php

namespace App\Services\Sentiment;

interface SentimentAnalyzerInterface
{
    /**
     * Analyze a text and return sentiment data.
     *
     * @param  array<string, mixed>  $context
     * @return array{
     *     label:string,
     *     score:float,
     *     confidence?:float|null,
     *     method?:string|null,
     *     matched_positive_terms?:array<int, string>,
     *     matched_negative_terms?:array<int, string>,
     *     reason_summary?:string|null
     * }
     */
    public function analyze(string $text, array $context = []): array;
}
