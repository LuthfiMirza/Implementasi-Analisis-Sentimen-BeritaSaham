<?php

namespace App\Services\Research;

use App\Models\TradeResearchArtifact;
use App\Models\TradeResearchArtifactDependency;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;

class ResearchArtifactRegistryService
{
    public function __construct(
        protected ResearchArtifactValidationService $validator,
        protected ?array $config = null,
    ) {
        $this->config ??= config('trading_research');
    }

    public function register(string $path, bool $force = false, bool $verifyDependencies = false, bool $quarantineInvalid = false): array
    {
        $result = $this->validator->validate($path);
        if (! $result['valid']) {
            return ['status' => $quarantineInvalid ? 'quarantined' : 'invalid', 'validation' => $result, 'artifact' => null];
        }

        return DB::transaction(function () use ($result, $path, $force, $verifyDependencies) {
            $existing = TradeResearchArtifact::where('checksum', $result['checksum'])->first();
            if ($existing && ! $force) {
                if ($verifyDependencies) {
                    $this->syncDependencies($existing, $result['dependencies']);
                }
                return ['status' => 'unchanged', 'validation' => $result, 'artifact' => $existing->fresh('dependencies')];
            }

            $conflict = TradeResearchArtifact::where('logical_identity', $result['logical_identity'])
                ->where('checksum', '!=', $result['checksum'])
                ->exists();

            $notes = [];
            $warnings = $result['warnings'];
            $validationStatus = $result['validation_status'];
            $isQuarantined = false;
            if ($conflict) {
                $warnings[] = 'logical_identity_conflict';
                $notes['logical_identity_conflict'] = true;
                $validationStatus = 'logical_identity_conflict';
                $isQuarantined = (bool) ($this->config['quarantine_policy']['quarantine_conflicts'] ?? true);
            }

            $isStale = $this->isStale($result['artifact_type'], $result['generated_at']);
            if ($isStale) {
                $warnings[] = 'stale artifact';
            }
            $qualityGrade = $this->qualityGradeWithWarnings($result['quality_grade'], $warnings);
            $usageTier = $isQuarantined ? 'none' : $result['usage_tier'];
            $usableResearch = ! $isQuarantined && (bool) $result['usable_for_research'];
            $usableDecision = ! $isQuarantined && ! $isStale && (bool) $result['usable_for_decision'];

            $artifact = TradeResearchArtifact::create([
                'ticker' => $result['ticker'],
                'artifact_type' => $result['artifact_type'],
                'schema_version' => $result['schema_version'],
                'generator_version' => $result['generator_version'],
                'artifact_path' => $path,
                'artifact_filename' => basename($path),
                'checksum_algorithm' => $result['checksum_algorithm'],
                'checksum' => $result['checksum'],
                'file_size' => $result['file_size'],
                'generated_at' => $result['generated_at'],
                'imported_at' => now(),
                'data_start' => $result['data_start'],
                'data_end' => $result['data_end'],
                'source_event_count' => $result['source_event_count'],
                'validation_status' => $validationStatus,
                'usage_tier' => $usageTier,
                'quality_status' => $result['quality_status'],
                'quality_grade' => $qualityGrade,
                'usable_for_research' => $usableResearch,
                'usable_for_decision' => $usableDecision,
                'selected_available' => $result['selected_available'],
                'warning_count' => count($warnings),
                'critical_warning_count' => $this->countWarnings($warnings, 'critical'),
                'informational_warning_count' => $this->countWarnings($warnings, 'informational'),
                'warnings' => array_values(array_unique($warnings)),
                'limitations' => $result['limitations'],
                'summary' => $result['summary'],
                'quality_snapshot' => $result['quality_snapshot'],
                'source_snapshot' => $result['source_snapshot'],
                'registry_notes' => $notes,
                'logical_identity' => $result['logical_identity'],
                'is_latest' => false,
                'is_stale' => $isStale,
                'is_quarantined' => $isQuarantined,
            ]);

            $this->syncDependencies($artifact, $result['dependencies']);
            $this->refreshLatest($result['ticker'], $result['artifact_type']);

            return ['status' => $conflict ? 'conflict' : 'imported', 'validation' => $result, 'artifact' => $artifact->fresh('dependencies')];
        });
    }

    public function syncDependencies(TradeResearchArtifact $artifact, array $dependencies): void
    {
        $artifact->dependencies()->delete();
        foreach ($dependencies as $dependency) {
            $resolved = $this->resolveDependency($artifact, $dependency);
            TradeResearchArtifactDependency::create(array_merge($dependency, $resolved, ['artifact_id' => $artifact->id]));
        }
    }

    protected function resolveDependency(TradeResearchArtifact $artifact, array $dependency): array
    {
        if (($dependency['dependency_type'] ?? null) === 'external_source') {
            $resolvedPath = $this->resolveExpectedPath($dependency['expected_path'] ?? null);
            $checksum = $resolvedPath && File::exists($resolvedPath) ? hash_file($this->config['checksum_algorithm'], $resolvedPath) : null;
            return [
                'depends_on_artifact_id' => null,
                'resolved_path' => $resolvedPath,
                'resolved_checksum' => $checksum,
                'resolution_status' => $resolvedPath ? 'external_source' : 'missing_file',
            ];
        }

        $query = TradeResearchArtifact::query();
        if (! empty($dependency['expected_checksum'])) {
            $query->where('checksum', $dependency['expected_checksum']);
        }
        if (! empty($dependency['expected_artifact_type'])) {
            $query->where('artifact_type', $dependency['expected_artifact_type']);
        }
        if (! empty($dependency['expected_schema_version'])) {
            $query->where('schema_version', $dependency['expected_schema_version']);
        }
        $query->where('ticker', $artifact->ticker);
        $record = $query->orderByDesc('generated_at')->first();

        if (! $record) {
            $path = $this->resolveExpectedPath($dependency['expected_path'] ?? null);
            return [
                'depends_on_artifact_id' => null,
                'resolved_path' => $path,
                'resolved_checksum' => $path && File::exists($path) ? hash_file($this->config['checksum_algorithm'], $path) : null,
                'resolution_status' => $path ? 'unresolved' : 'missing_file',
            ];
        }

        $status = 'resolved';
        if (! empty($dependency['expected_checksum']) && $dependency['expected_checksum'] !== $record->checksum) {
            $status = 'checksum_mismatch';
        } elseif (! empty($dependency['expected_schema_version']) && $dependency['expected_schema_version'] !== $record->schema_version) {
            $status = 'schema_mismatch';
        } elseif ($record->ticker !== $artifact->ticker) {
            $status = 'ticker_mismatch';
        }

        return [
            'depends_on_artifact_id' => $record->id,
            'resolved_path' => $record->artifact_path,
            'resolved_checksum' => $record->checksum,
            'resolution_status' => $status,
        ];
    }

    public function verifyRecord(int $artifactId, bool $quarantineInvalid = false, bool $repairLatest = false): array
    {
        $artifact = TradeResearchArtifact::findOrFail($artifactId);
        $warnings = $artifact->warnings ?? [];
        $status = 'valid';
        if (! File::exists($artifact->artifact_path)) {
            $status = 'missing_file';
            $warnings[] = 'missing_file';
        } else {
            $checksum = hash_file($artifact->checksum_algorithm, $artifact->artifact_path);
            if ($checksum !== $artifact->checksum) {
                $status = 'checksum_mismatch';
                $warnings[] = 'file modified after import';
            }
        }
        if ($this->isStale($artifact->artifact_type, $artifact->generated_at)) {
            $artifact->is_stale = true;
            $warnings[] = 'stale artifact';
        }
        if ($quarantineInvalid && $status !== 'valid') {
            $artifact->is_quarantined = true;
            $artifact->usage_tier = 'none';
            $artifact->usable_for_research = false;
            $artifact->usable_for_decision = false;
        }
        $artifact->warnings = array_values(array_unique($warnings));
        $artifact->warning_count = count($artifact->warnings);
        $artifact->validation_status = $status === 'valid' ? $artifact->validation_status : $status;
        $artifact->save();
        $this->syncDependencies($artifact, $this->validator->validate($artifact->artifact_path)['dependencies'] ?? []);
        if ($repairLatest) {
            $this->refreshLatest($artifact->ticker, $artifact->artifact_type);
        }
        return ['status' => $status, 'artifact' => $artifact->fresh('dependencies')];
    }

    public function latestValid(string $ticker, string $artifactType): ?TradeResearchArtifact
    {
        return TradeResearchArtifact::forTicker($ticker)->ofType($artifactType)->valid()->notQuarantined()->where('is_latest', true)->first();
    }

    public function latestResearchUsable(string $ticker, string $artifactType): ?TradeResearchArtifact
    {
        return TradeResearchArtifact::forTicker($ticker)->ofType($artifactType)->valid()->researchUsable()->notQuarantined()->where('is_latest', true)->first();
    }

    public function latestDecisionUsable(string $ticker, string $artifactType): ?TradeResearchArtifact
    {
        return TradeResearchArtifact::forTicker($ticker)->ofType($artifactType)->valid()->decisionUsable()->notStale()->notQuarantined()->where('is_latest', true)->first();
    }

    public function history(string $ticker, string $artifactType)
    {
        return TradeResearchArtifact::forTicker($ticker)->ofType($artifactType)->history()->get();
    }

    public function dependencies(int $artifactId)
    {
        return TradeResearchArtifact::findOrFail($artifactId)->dependencies()->get();
    }

    public function availabilitySummary(string $ticker): array
    {
        $types = array_keys($this->config['supported_artifact_types']);
        $summary = ['ticker' => strtoupper($ticker), 'artifact_types' => [], 'all_required_research_available' => true, 'all_required_decision_usable' => true, 'warnings' => []];
        foreach ($types as $type) {
            $valid = $this->latestValid($ticker, $type);
            $research = $this->latestResearchUsable($ticker, $type);
            $decision = $this->latestDecisionUsable($ticker, $type);
            $summary['artifact_types'][$type] = [
                'latest_valid' => $valid !== null,
                'research_usable' => $research !== null,
                'decision_usable' => $decision !== null,
                'quality_grade' => $valid?->quality_grade,
                'is_stale' => (bool) ($valid?->is_stale ?? false),
                'dependency_status' => $valid ? $valid->dependencies()->pluck('resolution_status')->unique()->values()->all() : [],
            ];
            $summary['all_required_research_available'] = $summary['all_required_research_available'] && $research !== null;
            $summary['all_required_decision_usable'] = $summary['all_required_decision_usable'] && $decision !== null;
        }
        return $summary;
    }

    public function artifactStatus(string $ticker, string $artifactType): array
    {
        $latest = $this->latestValid($ticker, $artifactType);
        if (! $latest) {
            return ['available' => false, 'reason' => 'no_valid_artifact', 'latest_research_available' => false];
        }
        return [
            'available' => true,
            'latest_valid_id' => $latest->id,
            'latest_research_available' => $this->latestResearchUsable($ticker, $artifactType) !== null,
            'latest_decision_available' => $this->latestDecisionUsable($ticker, $artifactType) !== null,
            'decision_unavailable_reason' => $this->latestDecisionUsable($ticker, $artifactType) ? null : 'no_decision_usable_artifact',
        ];
    }

    public function refreshLatest(string $ticker, string $type): void
    {
        TradeResearchArtifact::forTicker($ticker)->ofType($type)->update(['is_latest' => false]);
        $latest = TradeResearchArtifact::forTicker($ticker)->ofType($type)->valid()->notQuarantined()
            ->where('validation_status', 'valid')->orderByDesc('generated_at')->orderByDesc('id')->first();
        if ($latest) {
            TradeResearchArtifact::forTicker($ticker)->ofType($type)->where('id', '!=', $latest->id)->whereNull('superseded_by_id')->update(['superseded_by_id' => $latest->id]);
            $latest->forceFill(['is_latest' => true])->save();
        }
    }

    protected function isStale(string $type, mixed $generatedAt): bool
    {
        if (! $generatedAt) return false;
        $days = (int) ($this->config['staleness_days'][$type] ?? 3650);
        return Carbon::parse($generatedAt)->lt(now()->subDays($days));
    }

    protected function countWarnings(array $warnings, string $kind): int
    {
        $keywords = $this->config['warning_classification'][$kind.'_keywords'] ?? [];
        return collect($warnings)->filter(fn ($warning) => collect($keywords)->contains(fn ($keyword) => str_contains((string) $warning, $keyword)))->count();
    }

    protected function qualityGradeWithWarnings(?string $current, array $warnings): string
    {
        $joined = implode(' ', $warnings);
        foreach ($this->config['quality_classification']['critical_warning_keywords'] as $keyword) {
            if (str_contains($joined, $keyword)) return 'critical';
        }
        foreach ($this->config['quality_classification']['limited_warning_keywords'] as $keyword) {
            if (str_contains($joined, $keyword)) return 'limited';
        }
        return $current ?: ($warnings ? 'warning' : 'healthy');
    }

    protected function resolveExpectedPath(?string $path): ?string
    {
        if (! $path) return null;
        $candidate = str_starts_with($path, DIRECTORY_SEPARATOR) ? $path : base_path($path);
        return realpath($candidate) ?: $candidate;
    }
}
