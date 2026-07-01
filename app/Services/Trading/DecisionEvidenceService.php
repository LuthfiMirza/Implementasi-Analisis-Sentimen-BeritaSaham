<?php

namespace App\Services\Trading;

use App\Models\TradeResearchArtifact;
use App\Services\Research\ResearchArtifactRegistryService;

class DecisionEvidenceService
{
    public function __construct(
        protected ResearchArtifactRegistryService $registry,
        protected ?array $config = null,
    ) {
        $this->config ??= config('trading_research.decision');
    }

    public function resolve(string $ticker): array
    {
        $types = array_values(array_unique(array_merge(
            $this->config['required_research_artifacts'],
            $this->config['required_decision_artifacts'],
            $this->config['optional_artifacts'],
        )));

        $evidence = [];
        foreach ($types as $type) {
            $valid = $this->registry->latestValid($ticker, $type);
            $research = $this->registry->latestResearchUsable($ticker, $type);
            $decision = $this->registry->latestDecisionUsable($ticker, $type);
            $evidence[$type] = [
                'latest_valid_available' => $valid !== null,
                'latest_research_available' => $research !== null,
                'latest_decision_available' => $decision !== null,
                'latest_valid' => $this->snapshot($valid),
                'latest_research' => $this->snapshot($research),
                'latest_decision' => $this->snapshot($decision),
                'quality_grade' => $valid?->quality_grade,
                'selected_available' => (bool) ($valid?->selected_available ?? false),
                'is_stale' => (bool) ($valid?->is_stale ?? false),
                'is_quarantined' => (bool) ($valid?->is_quarantined ?? false),
                'dependency_status' => $valid ? $valid->dependencies()->pluck('resolution_status')->unique()->values()->all() : [],
                'warnings' => $valid?->warnings ?? [],
            ];
        }

        return $evidence;
    }

    protected function snapshot(?TradeResearchArtifact $artifact): ?array
    {
        if (! $artifact) {
            return null;
        }
        return [
            'id' => $artifact->id,
            'ticker' => $artifact->ticker,
            'artifact_type' => $artifact->artifact_type,
            'schema_version' => $artifact->schema_version,
            'checksum' => $artifact->checksum,
            'generated_at' => optional($artifact->generated_at)?->toIso8601String(),
            'validation_status' => $artifact->validation_status,
            'usage_tier' => $artifact->usage_tier,
            'quality_grade' => $artifact->quality_grade,
            'selected_available' => (bool) $artifact->selected_available,
            'is_stale' => (bool) $artifact->is_stale,
            'is_quarantined' => (bool) $artifact->is_quarantined,
            'dependency_status' => $artifact->dependencies()->pluck('resolution_status')->unique()->values()->all(),
        ];
    }
}
