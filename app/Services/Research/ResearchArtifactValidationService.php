<?php

namespace App\Services\Research;

use Illuminate\Support\Arr;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\File;

class ResearchArtifactValidationService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_research');
    }

    public function validate(string $path, ?string $expectedTicker = null, ?string $expectedType = null): array
    {
        $algorithm = $this->config['checksum_algorithm'] ?? 'sha256';
        $base = [
            'valid' => false,
            'validation_status' => 'missing_file',
            'path' => $path,
            'checksum_algorithm' => $algorithm,
            'checksum' => null,
            'file_size' => 0,
            'warnings' => [],
            'limitations' => [],
            'dependencies' => [],
        ];

        if (! File::exists($path)) {
            return $base;
        }

        $base['file_size'] = File::size($path);
        $base['checksum'] = hash_file($algorithm, $path);
        if ($base['file_size'] > (int) $this->config['maximum_file_size']) {
            return $this->invalid($base, 'invalid_schema', ['file exceeds maximum size']);
        }

        $payload = json_decode((string) File::get($path), true, (int) $this->config['maximum_json_depth']);
        if (! is_array($payload)) {
            return $this->invalid($base, 'invalid_json', ['invalid JSON']);
        }

        foreach (['schema_version', 'artifact_type', 'ticker', 'generated_at'] as $field) {
            if (! array_key_exists($field, $payload)) {
                return $this->invalid($base, 'missing_required_field', ["missing {$field}"], $payload);
            }
        }

        $artifactType = (string) $payload['artifact_type'];
        $schema = (string) $payload['schema_version'];
        $ticker = strtoupper((string) $payload['ticker']);

        if ($expectedTicker !== null && $ticker !== strtoupper($expectedTicker)) {
            return $this->invalid($base, 'ticker_mismatch', ['ticker mismatch'], $payload);
        }
        if ($expectedType !== null && $artifactType !== $expectedType) {
            return $this->invalid($base, 'invalid_schema', ['artifact type mismatch'], $payload);
        }
        if (! in_array($schema, $this->config['supported_artifact_types'][$artifactType] ?? [], true)) {
            return $this->invalid($base, 'unsupported_schema', ["unsupported schema {$schema}"], $payload);
        }

        try {
            $generatedAt = Carbon::parse((string) $payload['generated_at']);
        } catch (\Throwable) {
            return $this->invalid($base, 'invalid_generated_at', ['invalid generated_at'], $payload);
        }

        $quality = is_array($payload['quality'] ?? null) ? $payload['quality'] : [];
        $source = is_array($payload['source'] ?? null) ? $payload['source'] : [];
        $warnings = $this->extractWarnings($payload);
        $limitations = $this->extractLimitations($payload);
        $usage = $this->extractUsage($payload);
        $qualityGrade = $this->qualityGrade($payload, $warnings, $limitations);
        $dataRange = $this->extractDataRange($payload, $source);
        $sourceCount = $this->extractSourceCount($payload);

        return array_merge($base, [
            'valid' => true,
            'validation_status' => 'valid',
            'ticker' => $ticker,
            'artifact_type' => $artifactType,
            'schema_version' => $schema,
            'generator_version' => $payload['generator_version'] ?? null,
            'generated_at' => $generatedAt,
            'data_start' => $dataRange['start'],
            'data_end' => $dataRange['end'],
            'source_event_count' => $sourceCount,
            'quality_status' => $quality['status'] ?? null,
            'usage_tier' => $usage['usage_tier'],
            'usable_for_research' => $usage['usable_for_research'],
            'usable_for_decision' => $usage['usable_for_decision'],
            'selected_available' => $usage['selected_available'],
            'quality_grade' => $qualityGrade,
            'warnings' => $warnings,
            'limitations' => $limitations,
            'summary' => $this->extractSummary($payload),
            'quality_snapshot' => $quality,
            'source_snapshot' => $source,
            'dependencies' => $this->extractDependencies($payload),
            'logical_identity' => $this->logicalIdentity($ticker, $artifactType, $schema, (string) $payload['generated_at'], $payload['generator_version'] ?? null),
            'payload' => $payload,
        ]);
    }

    protected function invalid(array $base, string $status, array $warnings, array $payload = []): array
    {
        return array_merge($base, [
            'validation_status' => $status,
            'warnings' => $warnings,
            'payload' => $payload,
            'usage_tier' => 'none',
            'usable_for_research' => false,
            'usable_for_decision' => false,
            'selected_available' => false,
            'quality_grade' => 'critical',
            'dependencies' => [],
            'logical_identity' => null,
        ]);
    }

    protected function extractUsage(array $payload): array
    {
        $quality = is_array($payload['quality'] ?? null) ? $payload['quality'] : [];
        $usableResearch = (bool) ($quality['usable_for_reentry_research'] ?? $quality['usable_for_recovery_analysis'] ?? $quality['usable_for_risk_analysis'] ?? $quality['usable_for_research'] ?? false);
        if (! $usableResearch && in_array($payload['artifact_type'] ?? '', ['walk_forward_event_dataset','trade_episode_dataset','event_dataset_quality','event_quality_report','tp_optimizer','sl_optimizer'], true)) {
            $usableResearch = (($quality['status'] ?? null) !== 'invalid') || (($quality['event_count'] ?? 0) > 0);
        }
        $usableDecision = (bool) ($quality['usable_for_decision'] ?? false);
        $selectedAvailable = array_key_exists('selected', $payload) && $payload['selected'] !== null;
        if ($usableDecision && ($this->config['selected_null_policy']['decision_requires_selected'] ?? true)) {
            $usableDecision = $selectedAvailable || ! in_array($payload['artifact_type'] ?? '', ['tp_optimizer','sl_optimizer','reentry_research'], true);
        }
        return [
            'usable_for_research' => $usableResearch,
            'usable_for_decision' => $usableDecision,
            'selected_available' => $selectedAvailable,
            'usage_tier' => $usableDecision ? 'decision_usable' : ($usableResearch ? 'research_only' : 'none'),
        ];
    }

    protected function extractWarnings(array $payload): array
    {
        $warnings = [];
        foreach (['warnings','critical_warnings'] as $key) {
            foreach ((array) ($payload[$key] ?? []) as $warning) {
                $warnings[] = is_scalar($warning) ? (string) $warning : json_encode($warning);
            }
        }
        if (($payload['artifact_type'] ?? null) === 'reentry_research') {
            $rate = (float) Arr::get($payload, 'episode_accounting.unclassified_rate', 0);
            $threshold = (float) ($this->config['unclassified_rate_thresholds'][$payload['schema_version'] ?? ''] ?? 1);
            if ($rate > $threshold) {
                $warnings[] = 'high_unclassified_rate';
            }
        }
        if (Arr::get($payload, 'family_quality.atr_pullback.implementation_status') === 'implemented_but_unavailable') {
            $warnings[] = 'ATR family unavailable';
        }
        if (array_key_exists('selected', $payload) && $payload['selected'] === null) {
            $warnings[] = 'selected null';
        }
        return array_values(array_unique($warnings));
    }

    protected function extractLimitations(array $payload): array
    {
        $limitations = [];
        if (($payload['artifact_type'] ?? null) === 'reentry_research') {
            $limitations['unclassified'] = Arr::get($payload, 'episode_accounting');
            $limitations['atr_pullback'] = Arr::get($payload, 'family_quality.atr_pullback');
        }
        return $limitations;
    }

    protected function extractSummary(array $payload): array
    {
        return array_filter([
            'summary' => $payload['summary'] ?? null,
            'quality' => $payload['quality'] ?? null,
            'episode_accounting' => $payload['episode_accounting'] ?? null,
            'stream_accounting' => $payload['stream_accounting'] ?? null,
            'selected' => $payload['selected'] ?? null,
        ], fn ($value) => $value !== null);
    }

    protected function qualityGrade(array $payload, array $warnings, array $limitations): string
    {
        $joined = implode(' ', $warnings);
        foreach ($this->config['quality_classification']['critical_warning_keywords'] as $keyword) {
            if (str_contains($joined, $keyword)) {
                return 'critical';
            }
        }
        foreach ($this->config['quality_classification']['limited_warning_keywords'] as $keyword) {
            if (str_contains($joined, $keyword)) {
                return 'limited';
            }
        }
        return $warnings === [] ? 'healthy' : 'warning';
    }

    protected function extractDataRange(array $payload, array $source): array
    {
        return [
            'start' => $source['data_start'] ?? $payload['observation_summary']['data_start'] ?? $payload['episode_summary']['data_start'] ?? null,
            'end' => $source['data_end'] ?? $payload['observation_summary']['data_end'] ?? $payload['episode_summary']['data_end'] ?? null,
        ];
    }

    protected function extractSourceCount(array $payload): ?int
    {
        foreach (['episode_accounting.source_episode_count','quality.episode_count','quality.event_count','observation_summary.event_count','episode_summary.episode_count'] as $key) {
            $value = Arr::get($payload, $key);
            if (is_numeric($value)) {
                return (int) $value;
            }
        }
        if (isset($payload['events']) && is_array($payload['events'])) return count($payload['events']);
        if (isset($payload['episodes']) && is_array($payload['episodes'])) return count($payload['episodes']);
        return null;
    }

    protected function extractDependencies(array $payload): array
    {
        $source = is_array($payload['source'] ?? null) ? $payload['source'] : [];
        $deps = [];
        $map = [
            'event_artifact' => ['event_artifact_path','event_artifact_schema','event_artifact_checksum','walk_forward_event_dataset'],
            'episode_artifact' => ['episode_artifact_path','episode_artifact_schema','episode_artifact_checksum','trade_episode_dataset'],
            'tp_artifact' => ['TP artifact path','TP artifact schema','TP artifact checksum','tp_optimizer'],
            'tp_artifact_alt' => ['tp_artifact_path','tp_artifact_schema','tp_artifact_checksum','tp_optimizer'],
            'sl_artifact' => ['sl_artifact_path','sl_artifact_schema','sl_artifact_checksum','sl_optimizer'],
        ];
        foreach ($map as $role => [$pathKey,$schemaKey,$checksumKey,$type]) {
            if (isset($source[$pathKey]) || isset($source[$checksumKey])) {
                $deps[] = [
                    'dependency_type' => 'artifact',
                    'dependency_role' => str_replace('_alt', '', $role),
                    'expected_path' => $source[$pathKey] ?? null,
                    'expected_artifact_type' => $type,
                    'expected_schema_version' => $source[$schemaKey] ?? null,
                    'expected_checksum' => $source[$checksumKey] ?? null,
                    'is_required' => true,
                    'metadata' => [],
                ];
            }
        }
        foreach (['ohlcv_path','OHLCV path','canonical_ohlcv_path'] as $pathKey) {
            if (isset($source[$pathKey])) {
                $deps[] = [
                    'dependency_type' => 'external_source',
                    'dependency_role' => 'canonical_ohlcv',
                    'expected_path' => $source[$pathKey],
                    'expected_artifact_type' => null,
                    'expected_schema_version' => null,
                    'expected_checksum' => $source['ohlcv_checksum'] ?? $source['OHLCV checksum'] ?? null,
                    'is_required' => true,
                    'metadata' => ['source_key' => $pathKey],
                ];
            }
        }
        return $deps;
    }

    protected function logicalIdentity(string $ticker, string $type, string $schema, string $generatedAt, ?string $generator): string
    {
        return implode('|', [$ticker, $type, $schema, $generatedAt, $generator ?? '']);
    }
}
