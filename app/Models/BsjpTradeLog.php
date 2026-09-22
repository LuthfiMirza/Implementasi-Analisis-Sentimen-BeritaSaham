<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class BsjpTradeLog extends Model
{
    use HasFactory;

    protected $table = 'bsjp_trade_logs';

    protected $fillable = [
        'signal_date',
        'ticker',
        'stock_name',
        'category',
        'signal_price',
        'vol_ratio',
        'transaction_value',
        'target_tp',
        'stop_loss',
        'status',
        'capital_allocated',
        'lots',
        'entry_price',
        'entry_at',
        'exit_price',
        'exited_at',
        'exit_type',
        'gross_pnl_pct',
        'net_pnl_pct',
        'net_pnl_rp',
        'notes',
    ];

    protected $casts = [
        'signal_date' => 'date',
        'signal_price' => 'float',
        'vol_ratio' => 'float',
        'transaction_value' => 'float',
        'target_tp' => 'float',
        'stop_loss' => 'float',
        'capital_allocated' => 'float',
        'lots' => 'integer',
        'entry_price' => 'float',
        'entry_at' => 'datetime',
        'exit_price' => 'float',
        'exited_at' => 'datetime',
        'gross_pnl_pct' => 'float',
        'net_pnl_pct' => 'float',
        'net_pnl_rp' => 'float',
    ];

    public function stock(): BelongsTo
    {
        return $this->belongsTo(Stock::class, 'ticker', 'code');
    }

    public function scopeOpen(Builder $query): Builder
    {
        return $query->where('status', 'OPEN');
    }

    public function scopeClosed(Builder $query): Builder
    {
        return $query->where('status', 'CLOSED');
    }

    public function scopePending(Builder $query): Builder
    {
        return $query->where('status', 'PENDING');
    }

    /**
     * Hitung jumlah lot maksimal yang dapat dibeli dengan modal dan memperhitungkan fee beli 0.15%.
     */
    public static function calculateLots(float $capital, float $price, float $buyFeeRate = 0.0015): int
    {
        if ($price <= 0 || $capital <= 0) {
            return 0;
        }

        $costPerLot = $price * 100 * (1 + $buyFeeRate);
        return (int) floor($capital / $costPerLot);
    }

    /**
     * Hitung kalkulasi PnL secara akurat memperhitungkan fee round-trip broker.
     */
    public static function calculatePnl(
        float $entryPrice,
        float $exitPrice,
        int $lots,
        float $buyFeeRate = 0.0015,
        float $sellFeeRate = 0.0025
    ): array {
        if ($entryPrice <= 0 || $lots <= 0) {
            return [
                'gross_pnl_pct' => 0.0,
                'net_pnl_pct' => 0.0,
                'net_pnl_rp' => 0.0,
                'total_cost' => 0.0,
                'net_proceeds' => 0.0,
            ];
        }

        $totalCost = $lots * 100 * $entryPrice * (1 + $buyFeeRate);
        $grossProceeds = $lots * 100 * $exitPrice;
        $netProceeds = $grossProceeds * (1 - $sellFeeRate);
        $netPnlRp = $netProceeds - $totalCost;

        $grossPnlPct = (($exitPrice - $entryPrice) / $entryPrice) * 100;
        $netPnlPct = ($netPnlRp / $totalCost) * 100;

        return [
            'gross_pnl_pct' => round($grossPnlPct, 2),
            'net_pnl_pct' => round($netPnlPct, 2),
            'net_pnl_rp' => round($netPnlRp, 0),
            'total_cost' => round($totalCost, 0),
            'net_proceeds' => round($netProceeds, 0),
        ];
    }

    /**
     * Tutup posisi trade dan simpan perhitungan PnL otomatis.
     */
    public function closeTrade(float $exitPrice, ?\Carbon\Carbon $exitedAt = null, string $notes = '', string $exitType = 'OPEN_MARKET'): void
    {
        $exitedAt = $exitedAt ?? now('Asia/Jakarta');
        $entryPrice = (float) ($this->entry_price ?: $this->signal_price);
        $pnl = self::calculatePnl($entryPrice, $exitPrice, $this->lots);

        $this->update([
            'exit_price' => $exitPrice,
            'exited_at' => $exitedAt,
            'exit_type' => $exitType,
            'gross_pnl_pct' => $pnl['gross_pnl_pct'],
            'net_pnl_pct' => $pnl['net_pnl_pct'],
            'net_pnl_rp' => $pnl['net_pnl_rp'],
            'status' => 'CLOSED',
            'notes' => $notes ?: $this->notes,
        ]);
    }
}
