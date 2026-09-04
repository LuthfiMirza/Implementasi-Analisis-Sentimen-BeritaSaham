<?php

namespace App\Console\Commands;

use App\Models\SelfRadarSignalLog;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('research:self-radar-log {ticker} {--date=} {--fill=} {--exit=}')]
#[Description('Catat fill/exit manual untuk SELF_RADAR_V1_TOP5')]
class UpdateSelfRadarSignalLogCommand extends Command
{
    public function handle(): int
    {
        $ticker = strtoupper((string) $this->argument('ticker'));
        $date = $this->option('date') ?: now('Asia/Jakarta')->toDateString();

        $log = SelfRadarSignalLog::query()
            ->where('ticker', $ticker)
            ->whereDate('signal_date', $date)
            ->first();

        if (! $log) {
            $this->error("Log {$ticker} {$date} belum ada.");

            return self::FAILURE;
        }

        if ($this->option('fill') !== null) {
            $log->fill_price = (float) $this->option('fill');
            $log->filled_at = now('Asia/Jakarta');
        }

        if ($this->option('exit') !== null) {
            $log->exit_price = (float) $this->option('exit');
            $log->exited_at = now('Asia/Jakarta');
        }

        if ($log->fill_price && $log->exit_price) {
            $log->pnl_pct = round(((float) $log->exit_price / (float) $log->fill_price - 1) * 100, 2);
            $log->result = $log->pnl_pct > 0 ? 'WIN' : ($log->pnl_pct < 0 ? 'LOSS' : 'DRAW');
        }

        $log->save();

        $this->info(sprintf(
            '%s %s fill=%s exit=%s pnl=%s result=%s',
            $log->ticker,
            $log->signal_date->toDateString(),
            $log->fill_price ?? '-',
            $log->exit_price ?? '-',
            $log->pnl_pct ?? '-',
            $log->result ?? '-',
        ));

        return self::SUCCESS;
    }
}
