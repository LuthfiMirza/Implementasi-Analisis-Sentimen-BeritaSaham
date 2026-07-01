<?php

namespace App\Services\Trading;

class ReasonEngineService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_confidence.reason');
    }

    public function build(array $context): array
    {
        $reasons = [];
        foreach ($context['base_reasons'] as $reason) {
            $reasons[] = $this->normalizeBaseReason($reason);
        }
        $reasons[] = $this->reason('CONFIDENCE_STATUS_'.$context['confidence']['status'], 'confidence', 'informational', 'neutral', 'confidence', 'Confidence status is '.$context['confidence']['status'].'.', ['type' => 'confidence'], ['score' => $context['confidence']['evidence_confidence']['score']]);
        foreach ($context['confidence']['evidence_confidence']['components'] as $component) {
            if (($component['raw_score'] ?? 0) < 60) {
                $reasons[] = $this->reason('CONFIDENCE_COMPONENT_'.strtoupper($component['key']), 'confidence', 'warning', 'negative', 'confidence', 'Confidence component '.$component['key'].' is limited.', ['type' => 'confidence_component', 'component' => $component['key']], $component);
            }
        }
        $reasons = $this->dedupe($reasons);
        $reasons = $this->sortReasons($reasons);
        foreach ($reasons as $index => &$reason) {
            $reason['rank'] = $index + 1;
        }
        unset($reason);
        return [
            'schema_version' => $this->config['schema_version'],
            'reasons' => $reasons,
            'summary' => $this->summary($reasons),
        ];
    }

    public function summary(array $reasons): array
    {
        $counts = collect($reasons)->countBy('severity');
        $blocker = $this->dominantBlocker($reasons);
        return [
            'total' => count($reasons),
            'critical_count' => (int) ($counts['critical'] ?? 0),
            'blocking_count' => (int) ($counts['blocking'] ?? 0),
            'warning_count' => (int) ($counts['warning'] ?? 0),
            'supportive_count' => (int) ($counts['supportive'] ?? 0),
            'informational_count' => (int) ($counts['informational'] ?? 0),
            'dominant_blocker' => $blocker['code'] ?? null,
            'dominant_blocker_policy' => 'configured_priority',
            'primary_reason_codes' => $this->primaryReasonCodes($reasons),
            'supporting_reason_codes' => collect($reasons)->where('severity', 'supportive')->pluck('code')->values()->all(),
            'diagnostic_reason_count' => collect($reasons)->whereIn('severity', ['warning','informational'])->count(),
        ];
    }

    protected function dominantBlocker(array $reasons): ?array
    {
        $blockers = collect($reasons)->whereIn('severity', ['critical','blocking'])->values();
        $priority = $this->config['dominant_blocker_priority'] ?? [];
        return $blockers->sortBy(fn($r) => array_search($r['code'], $priority, true) === false ? 999 : array_search($r['code'], $priority, true))->first();
    }

    protected function primaryReasonCodes(array $reasons): array
    {
        $desired = ['NO_DECISION_USABLE_TP','NO_DECISION_USABLE_SL','RESEARCH_ONLY_EVIDENCE','ACTION_SELECTION_NOT_IMPLEMENTED','ACTION_CAPABILITY_NOT_IMPLEMENTED','SAFE_DOWNGRADE_WAIT'];
        $codes = collect($reasons)->pluck('code');
        $primary = collect($desired)->filter(fn($c) => $codes->contains($c))->values();
        return $primary->take($this->config['primary_reason_limit'])->all();
    }

    protected function normalizeBaseReason(array $reason): array
    {
        $severity = $reason['severity'] ?? 'informational';
        return $this->reason(
            $reason['code'],
            $reason['category'] ?? $this->categoryFor($reason['code']),
            $severity,
            in_array($severity, ['blocking', 'critical', 'warning'], true) ? 'negative' : ($severity === 'supportive' ? 'positive' : 'neutral'),
            $this->impactFor($reason['category'] ?? '', $severity),
            $this->messageFor($reason['code'], $reason['message'] ?? ''),
            ['type' => ($reason['source']['artifact_type'] ?? null) ? 'registry_artifact' : 'service', 'artifact_type' => $reason['source']['artifact_type'] ?? null, 'registry_artifact_id' => $reason['source']['artifact_id'] ?? null, 'schema_version' => $reason['source']['schema_version'] ?? null],
            $reason['evidence'] ?? []
        );
    }

    protected function reason(string $code, string $category, string $severity, string $polarity, string $impact, string $message, array $source, array $evidence = []): array
    {
        return compact('code', 'category', 'severity', 'polarity', 'impact', 'message', 'source', 'evidence') + [
            'sources' => [$source],
            'source_count' => 1,
            'rank' => 0,
        ];
    }

    protected function dedupe(array $reasons): array
    {
        $byKey = [];
        foreach ($reasons as $reason) {
            $reason['sources'] = $reason['sources'] ?? [$reason['source']];
            $reason['source_count'] = count($reason['sources']);
            $key = $reason['code'].'|'.$reason['impact'];
            if (! isset($byKey[$key])) {
                $byKey[$key] = $reason;
                continue;
            }

            $byKey[$key]['sources'] = $this->mergeSources($byKey[$key]['sources'] ?? [$byKey[$key]['source']], $reason['sources']);
            $byKey[$key]['source_count'] = count($byKey[$key]['sources']);
            if ($this->severityRank($reason['severity']) < $this->severityRank($byKey[$key]['severity'])) {
                $reason['sources'] = $byKey[$key]['sources'];
                $reason['source_count'] = $byKey[$key]['source_count'];
                $byKey[$key] = $reason;
            }
        }
        return array_values($byKey);
    }

    protected function mergeSources(array $existing, array $incoming): array
    {
        $sources = [];
        foreach (array_merge($existing, $incoming) as $source) {
            $key = implode('|', [
                $source['type'] ?? '',
                $source['artifact_type'] ?? '',
                $source['registry_artifact_id'] ?? '',
                $source['schema_version'] ?? '',
                $source['component'] ?? '',
            ]);
            $sources[$key] = $source;
        }

        ksort($sources);
        return array_values($sources);
    }

    protected function sortReasons(array $reasons): array
    {
        usort($reasons, fn($a, $b) => [$this->severityRank($a['severity']), $this->categoryRank($a['category']), $a['code']] <=> [$this->severityRank($b['severity']), $this->categoryRank($b['category']), $b['code']]);
        return $reasons;
    }

    protected function severityRank(string $severity): int { return array_search($severity, $this->config['severity_order'], true) ?: 0; }
    protected function categoryRank(string $category): int { $idx = array_search($category, $this->config['category_order'], true); return $idx === false ? 999 : $idx; }
    protected function categoryFor(string $code): string { return str_contains($code, 'PREDICTION') ? 'prediction' : (str_contains($code, 'DEPENDENCY') ? 'dependency' : (str_contains($code, 'CONFIDENCE') ? 'confidence' : 'safety')); }
    protected function impactFor(string $category, string $severity): string { return in_array($severity, ['blocking','critical'], true) ? 'action' : ($category === 'confidence' ? 'confidence' : 'evidence'); }
    protected function messageFor(string $code, string $fallback): string { return $fallback !== '' ? $fallback : str_replace('_', ' ', strtolower($code)).'.'; }
}
