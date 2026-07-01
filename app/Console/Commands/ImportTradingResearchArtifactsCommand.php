<?php

namespace App\Console\Commands;

use App\Services\Research\ResearchArtifactDiscoveryService;
use App\Services\Research\ResearchArtifactRegistryService;
use App\Services\Research\ResearchArtifactValidationService;
use Illuminate\Console\Command;

class ImportTradingResearchArtifactsCommand extends Command
{
    protected $signature = 'trading-research:import-artifacts
        {--path=storage/app/trading_research}
        {--ticker=}
        {--type=}
        {--dry-run}
        {--force}
        {--verify-dependencies}
        {--quarantine-invalid}
        {--include-stale}
        {--json-output}';

    protected $description = 'Import trading research artifact metadata into the registry.';

    public function handle(ResearchArtifactDiscoveryService $discovery, ResearchArtifactRegistryService $registry, ResearchArtifactValidationService $validator): int
    {
        $summary = $this->emptySummary();
        try {
            $files = $discovery->discover($this->option('path'), $this->option('ticker') ?: null, $this->option('type') ?: null);
        } catch (\Throwable $exception) {
            $summary['invalid']++;
            $summary['errors'][] = $exception->getMessage();
            return $this->emit($summary, 1);
        }

        $summary['discovered'] = count($files);
        foreach ($files as $file) {
            try {
                if ($this->option('dry-run')) {
                    $validation = $validator->validate($file, $this->option('ticker') ?: null, $this->option('type') ?: null);
                    $validation['valid'] ? $summary['valid']++ : $summary['invalid']++;
                    $summary['planned'][] = $file;
                    continue;
                }
                $result = $registry->register($file, (bool) $this->option('force'), (bool) $this->option('verify-dependencies'), (bool) $this->option('quarantine-invalid'));
                $status = $result['status'];
                if (($result['validation']['valid'] ?? false) === true) $summary['valid']++;
                if (isset($summary[$status])) $summary[$status]++;
                if ($status === 'conflict') $summary['conflicts']++;
                if ($status === 'quarantined') $summary['quarantined']++;
                if (($result['artifact']?->is_stale ?? false) === true) $summary['stale']++;
                $unresolved = $result['artifact']?->dependencies()->whereIn('resolution_status', ['unresolved','missing_file','checksum_mismatch','schema_mismatch','ticker_mismatch'])->count() ?? 0;
                $summary['unresolved_dependencies'] += $unresolved;
            } catch (\Throwable $exception) {
                $summary['invalid']++;
                $summary['errors'][] = ['file' => $file, 'error' => $exception->getMessage()];
            }
        }

        return $this->emit($summary, 0);
    }

    protected function emptySummary(): array
    {
        return ['discovered'=>0,'valid'=>0,'imported'=>0,'unchanged'=>0,'superseded'=>0,'invalid'=>0,'conflicts'=>0,'conflict'=>0,'quarantined'=>0,'stale'=>0,'unresolved_dependencies'=>0,'planned'=>[],'errors'=>[]];
    }

    protected function emit(array $summary, int $code): int
    {
        if ($this->option('json-output')) {
            $this->line(json_encode($summary, JSON_PRETTY_PRINT));
        } else {
            foreach ($summary as $key => $value) {
                if (is_array($value)) continue;
                $this->line("{$key}: {$value}");
            }
        }
        return $code;
    }
}
