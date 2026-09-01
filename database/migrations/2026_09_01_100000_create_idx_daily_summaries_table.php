<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * End-of-day trading summary for every IDX stock, one row per stock per trade date.
 * Source: idx.co.id GetStockSummary (public EOD data). Powers the Market Alerts page
 * (volume spike / price gap / foreign flow). Descriptive monitoring only -- deliberately
 * decoupled from stock_prices and never fed into the prediction/DSS pipeline.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('idx_daily_summaries', function (Blueprint $table) {
            $table->id();
            $table->date('trade_date');
            $table->string('stock_code', 12);
            $table->string('stock_name')->nullable();
            $table->string('remarks', 64)->nullable();

            $table->decimal('previous', 18, 4)->nullable();
            $table->decimal('open', 18, 4)->nullable();
            $table->decimal('high', 18, 4)->nullable();
            $table->decimal('low', 18, 4)->nullable();
            $table->decimal('close', 18, 4)->nullable();
            $table->decimal('change', 18, 4)->nullable();
            $table->decimal('pct_change', 10, 4)->nullable();

            $table->unsignedBigInteger('volume')->default(0);
            $table->decimal('value', 24, 2)->default(0);
            $table->unsignedBigInteger('frequency')->default(0);

            // Foreign buy/sell are reported by IDX in shares (lembar), not rupiah.
            $table->bigInteger('foreign_buy')->default(0);
            $table->bigInteger('foreign_sell')->default(0);
            $table->bigInteger('foreign_net')->default(0);
            // Approximate rupiah value of the net foreign position (foreign_net * close).
            $table->decimal('foreign_net_value', 24, 2)->default(0);

            $table->unsignedBigInteger('listed_shares')->nullable();

            $table->string('source', 32)->default('idx_scrape');
            $table->timestamps();

            $table->unique(['trade_date', 'stock_code']);
            $table->index(['stock_code', 'trade_date']);
            $table->index('trade_date');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('idx_daily_summaries');
    }
};
