<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trades', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->foreignId('stock_id')->constrained()->onDelete('cascade');

            $table->string('signal_quality');
            $table->decimal('entry_price', 12, 2);
            $table->decimal('entry_zone_low', 12, 2)->nullable();
            $table->decimal('entry_zone_high', 12, 2)->nullable();
            $table->decimal('stop_loss', 12, 2);
            $table->decimal('target_1', 12, 2);
            $table->decimal('target_2', 12, 2)->nullable();
            $table->decimal('rr_ratio', 8, 2)->nullable();
            $table->integer('lot_size')->nullable();
            $table->decimal('position_value', 15, 2)->nullable();

            $table->decimal('dss_score', 8, 2)->nullable();
            $table->string('dss_status')->nullable();
            $table->string('dss_prediction')->nullable();
            $table->decimal('dss_confidence', 5, 2)->nullable();
            $table->decimal('sentiment_avg', 8, 4)->nullable();
            $table->json('indicators_snapshot')->nullable();

            $table->enum('status', ['open', 'closed', 'cancelled'])->default('open');
            $table->date('entry_date');
            $table->date('exit_date')->nullable();
            $table->decimal('exit_price', 12, 2)->nullable();
            $table->integer('holding_days')->nullable();

            $table->enum('result', ['hit_target_1', 'hit_target_2', 'stop_loss', 'manual_close', 'open'])->default('open');
            $table->decimal('pnl_per_share', 12, 2)->nullable();
            $table->decimal('pnl_total', 15, 2)->nullable();
            $table->decimal('pnl_percent', 8, 2)->nullable();
            $table->decimal('actual_rr', 8, 2)->nullable();

            $table->text('notes')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trades');
    }
};
