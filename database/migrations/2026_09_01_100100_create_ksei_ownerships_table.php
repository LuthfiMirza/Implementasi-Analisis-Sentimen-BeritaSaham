<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Monthly securities-ownership composition per stock from KSEI (local vs foreign, by investor
 * type). This is the free, structured substitute for a ">=1% shareholder" feed -- individual
 * holder names at that level are only in issuers' monthly reports and are not publicly
 * available in structured form. Aggregate only; one row per stock per month-end snapshot.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('ksei_ownerships', function (Blueprint $table) {
            $table->id();
            $table->date('snapshot_date');          // month-end the KSEI file represents
            $table->string('stock_code', 12);
            $table->string('stock_name')->nullable();

            $table->unsignedBigInteger('total_shares')->default(0);
            $table->unsignedBigInteger('local_shares')->default(0);
            $table->unsignedBigInteger('foreign_shares')->default(0);
            $table->decimal('local_pct', 8, 4)->default(0);
            $table->decimal('foreign_pct', 8, 4)->default(0);

            // Month-over-month change in foreign ownership percentage points.
            $table->decimal('foreign_pct_delta', 8, 4)->nullable();

            // Optional breakdown by investor type, kept as JSON to avoid a wide schema.
            $table->json('breakdown')->nullable();

            $table->string('source', 32)->default('ksei_scrape');
            $table->timestamps();

            $table->unique(['snapshot_date', 'stock_code']);
            $table->index(['stock_code', 'snapshot_date']);
            $table->index('snapshot_date');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('ksei_ownerships');
    }
};
