<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Arsip permanen bar intraday (default 15 menit) per emiten.
 *
 * Yahoo Finance hanya menyimpan riwayat 15m selama ~60 hari. Tanpa arsip ini, data menit yang
 * dipakai check_trailing_stop.py (puncak intraday, MFE, kronologi SL vs trailing) hilang
 * permanen setelah lewat 60 hari, dan riset MFE/trailing tidak bisa diulang.
 * Sengaja dipisah dari stock_prices supaya seri harian (1d) yang dipakai analitik tidak tercampur.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('intraday_prices', function (Blueprint $table) {
            $table->id();
            $table->string('stock_code', 16);
            $table->string('interval', 8)->default('15m');
            $table->dateTime('bar_time'); // waktu buka bar, Asia/Jakarta (WIB)
            $table->decimal('open', 14, 2);
            $table->decimal('high', 14, 2);
            $table->decimal('low', 14, 2);
            $table->decimal('close', 14, 2);
            $table->unsignedBigInteger('volume')->default(0);
            $table->string('source', 32)->default('yahoo_chart');
            $table->timestamps();

            $table->unique(['stock_code', 'interval', 'bar_time'], 'intraday_prices_code_interval_time_unique');
            $table->index(['bar_time']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('intraday_prices');
    }
};

