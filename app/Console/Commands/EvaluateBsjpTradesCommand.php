<?php

namespace App\Console\Commands;

use App\Models\BsjpTradeLog;
use App\Models\Stock;
use App\Services\MarketData\LiveMarketDataService;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class EvaluateBsjpTradesCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'trade:evaluate-bsjp 
                            {--auto-close : Automatically close open positions at market open price}
                            {--force : Force evaluation regardless of market time}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Evaluates active BSJP overnight positions against market open prices (09:00 WIB)';

    public function handle(LiveMarketDataService $liveMarketService): int
    {
        $this->info("=== Evaluasi Posisi BSJP (Beli Sore Jual Pagi) ===");

        $openTrades = BsjpTradeLog::where('status', 'OPEN')->get();

        if ($openTrades->isEmpty()) {
            $this->info("Tidak ada posisi BSJP yang berstatus OPEN.");
            return Command::SUCCESS;
        }

        $this->info("Ditemukan {$openTrades->count()} posisi OPEN yang perlu dievaluasi.");

        $autoClose = $this->option('auto-close');
        $force = $this->option('force');
        $now = Carbon::now('Asia/Jakarta');

        // Warning if market hasn't opened yet (typically < 09:00 WIB)
        if (!$force && $now->format('H:i') < '09:00') {
            $this->warn("Perhatian: Jam pasar belum menunjukkan pukul 09:00 WIB (sekarang: {$now->format('H:i')}). Gunakan --force jika ingin tetap mengecek harga terkini.");
            if (!$this->confirm("Lanjutkan pengecekan data pasar sekarang?", false)) {
                return Command::SUCCESS;
            }
        }

        $evaluated = 0;
        $closed = 0;

        foreach ($openTrades as $trade) {
            $ticker = strtoupper($trade->ticker);
            $entryPrice = (float) ($trade->entry_price ?: $trade->signal_price);
            $this->line("Memeriksa {$ticker} (Beli: Rp " . number_format($entryPrice, 0, ',', '.') . ")...");

            try {
                $stock = Stock::where('code', $ticker)->first();
                if (!$stock) {
                    $this->warn("  [!] Saham {$ticker} tidak ditemukan di database.");
                    continue;
                }

                $quote = $liveMarketService->quote($stock);

                if (!$quote || empty($quote['close'])) {
                    $this->warn("  [!] Gagal mengambil quote harga untuk {$ticker}.");
                    continue;
                }

                $openPrice = $quote['open'] ?? $quote['close'];
                $highPrice = $quote['high'] ?? $quote['close'];
                $currentPrice = $quote['close'] ?? $quote['last'];

                $openReturnPct = $entryPrice > 0 ? (($openPrice - $entryPrice) / $entryPrice) * 100 : 0;
                $currentReturnPct = $entryPrice > 0 ? (($currentPrice - $entryPrice) / $entryPrice) * 100 : 0;

                $this->info(sprintf(
                    "  [OK] %s | Open: Rp %s (%+.2f%%) | High: Rp %s | Now: Rp %s (%+.2f%%)",
                    $ticker,
                    number_format($openPrice, 0, ',', '.'),
                    $openReturnPct,
                    number_format($highPrice, 0, ',', '.'),
                    number_format($currentPrice, 0, ',', '.'),
                    $currentReturnPct
                ));

                if ($autoClose) {
                    $sellPrice = $openPrice;
                    $trade->closeTrade(
                        $sellPrice,
                        $now,
                        'Auto-closed via 09:05 WIB evaluator at market open price'
                    );
                    $this->info("  -> Posisi ditutup otomatis pada Rp " . number_format($sellPrice, 0, ',', '.') . " | Net PnL: Rp " . number_format($trade->net_pnl, 0, ',', '.'));
                    $closed++;
                }

                $evaluated++;
            } catch (\Exception $e) {
                $this->error("  Error saat evaluasi {$ticker}: " . $e->getMessage());
                Log::error("BSJP Evaluation error for {$ticker}: " . $e->getMessage());
            }
        }

        $this->info("Selesai. Evaluasi: {$evaluated} emiten, Ditutup: {$closed}.");
        return Command::SUCCESS;
    }
}
