<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add the lightweight trade journal contract columns while preserving the legacy DSS trade columns.
     */
    public function up(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            if (! Schema::hasColumn('trades', 'ticker')) {
                $table->string('ticker', 10)->nullable()->after('stock_id');
            }
            if (! Schema::hasColumn('trades', 'direction')) {
                $table->enum('direction', ['long', 'short'])->default('long')->after('ticker');
            }
            if (! Schema::hasColumn('trades', 'quantity')) {
                $table->integer('quantity')->nullable()->after('lot_size');
            }
            if (! Schema::hasColumn('trades', 'pnl')) {
                $table->decimal('pnl', 15, 2)->nullable()->after('pnl_total');
            }
            if (! Schema::hasColumn('trades', 'trade_date')) {
                $table->date('trade_date')->nullable()->after('entry_date');
            }
            if (! Schema::hasColumn('trades', 'closed_at')) {
                $table->timestamp('closed_at')->nullable()->after('exit_date');
            }
        });
    }

    /**
     * Remove only the compatibility columns added by this migration.
     */
    public function down(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            foreach (['ticker', 'direction', 'quantity', 'pnl', 'trade_date', 'closed_at'] as $column) {
                if (Schema::hasColumn('trades', $column)) {
                    $table->dropColumn($column);
                }
            }
        });
    }
};
