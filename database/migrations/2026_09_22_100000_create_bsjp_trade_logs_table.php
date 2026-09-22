<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('bsjp_trade_logs', function (Blueprint $table) {
            $table->id();
            $table->date('signal_date')->index();
            $table->string('ticker', 16)->index();
            $table->string('stock_name')->nullable();
            $table->string('category', 32)->default('sweetspot'); // 'sweetspot', 'rocket'
            $table->decimal('signal_price', 15, 2);
            $table->decimal('vol_ratio', 8, 2)->nullable();
            $table->decimal('transaction_value', 18, 2)->nullable();
            $table->decimal('target_tp', 15, 2)->nullable();
            $table->decimal('stop_loss', 15, 2)->nullable();
            $table->string('status', 20)->default('PENDING')->index(); // PENDING, OPEN, CLOSED, SKIPPED
            $table->decimal('capital_allocated', 15, 2)->default(20000000.00); // Default Rp 20 Jt
            $table->unsignedInteger('lots')->default(0);
            $table->decimal('entry_price', 15, 2)->nullable();
            $table->dateTime('entry_at')->nullable();
            $table->decimal('exit_price', 15, 2)->nullable();
            $table->dateTime('exited_at')->nullable();
            $table->string('exit_type', 30)->nullable(); // OPEN_MARKET, TARGET_TP, STOP_LOSS, MANUAL
            $table->decimal('gross_pnl_pct', 8, 2)->nullable();
            $table->decimal('net_pnl_pct', 8, 2)->nullable();
            $table->decimal('net_pnl_rp', 15, 2)->nullable();
            $table->text('notes')->nullable();
            $table->timestamps();

            $table->unique(['signal_date', 'ticker'], 'bsjp_trade_unique_signal');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('bsjp_trade_logs');
    }
};
