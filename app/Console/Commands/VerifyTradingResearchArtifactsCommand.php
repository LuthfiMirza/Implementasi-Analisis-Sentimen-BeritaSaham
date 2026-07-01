<?php

namespace App\Console\Commands;

use App\Models\TradeResearchArtifact;
use App\Services\Research\ResearchArtifactRegistryService;
use Illuminate\Console\Command;

class VerifyTradingResearchArtifactsCommand extends Command
{
    protected $signature = 'trading-research:verify-artifacts
        {--ticker=}
        {--type=}
        {--repair-latest}
        {--quarantine-invalid}
        {--include-stale}
        {--json-output}';

    protected $description = 'Verify imported trading research artifact registry records.';

    public function handle(ResearchArtifactRegistryService $registry): int
    {
        $query = TradeResearchArtifact::query();
        if ($this->option('ticker')) $query->forTicker($this->option('ticker'));
        if ($this->option('type')) $query->ofType($this->option('type'));
        if (! $this->option('include-stale')) $query->where('is_stale', false);

        $summary = ['checked'=>0,'valid'=>0,'missing_file'=>0,'checksum_mismatch'=>0,'stale'=>0,'quarantined'=>0,'repaired_latest'=>false,'errors'=>[]];
        foreach ($query->get() as $artifact) {
            try {
                $result = $registry->verifyRecord($artifact->id, (bool) $this->option('quarantine-invalid'), (bool) $this->option('repair-latest'));
                $summary['checked']++;
                $status = $result['status'];
                if (isset($summary[$status])) $summary[$status]++;
                if (($result['artifact']?->is_stale ?? false) === true) $summary['stale']++;
                if (($result['artifact']?->is_quarantined ?? false) === true) $summary['quarantined']++;
            } catch (\Throwable $exception) {
                $summary['errors'][] = ['id' => $artifact->id, 'error' => $exception->getMessage()];
            }
        }
        $summary['repaired_latest'] = (bool) $this->option('repair-latest');

        if ($this->option('json-output')) $this->line(json_encode($summary, JSON_PRETTY_PRINT));
        else foreach ($summary as $key => $value) if (! is_array($value)) $this->line("{$key}: {$value}");
        return 0;
    }
}
