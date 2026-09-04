<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('self_radar_signal_logs', function (Blueprint $table) {
            $table->id();
            $table->string('ticker', 16);
            $table->date('signal_date');
            $table->unsignedTinyInteger('rank')->nullable();
            $table->decimal('price_at_first_seen', 15, 2);
            $table->decimal('latest_price', 15, 2);
            $table->decimal('rsi14', 8, 2)->nullable();
            $table->decimal('ret_5d_pct', 8, 2)->nullable();
            $table->decimal('dd_20d_pct', 8, 2)->nullable();
            $table->decimal('score', 8, 2)->nullable();
            $table->dateTime('first_seen_at');
            $table->dateTime('last_seen_at');
            $table->dateTime('entry_window_start_at');
            $table->dateTime('entry_window_end_at');
            $table->dateTime('trailing_start_at');
            $table->decimal('fill_price', 15, 2)->nullable();
            $table->dateTime('filled_at')->nullable();
            $table->decimal('exit_price', 15, 2)->nullable();
            $table->dateTime('exited_at')->nullable();
            $table->string('result', 16)->nullable();
            $table->decimal('pnl_pct', 8, 2)->nullable();
            $table->timestamps();

            $table->unique(['ticker', 'signal_date']);
            $table->index(['signal_date', 'rank']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('self_radar_signal_logs');
    }
};
