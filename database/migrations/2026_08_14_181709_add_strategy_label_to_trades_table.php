<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            // Fase CA: sebelumnya "strategi" tiap trade cuma bisa ditebak dari substring notes
            // (rapuh -- match 'ai' pernah salah tangkap kata Indonesia biasa, lihat plan.md).
            // Kolom eksplisit ini jadi satu-satunya sumber kebenaran untuk kartu ringkasan resmi.
            $table->string('strategy_label', 30)->nullable()->after('notes')
                ->comment('gabungan|legacy_stock_only|legacy_ab_ac|momentum|ai_tp30|manual_discretionary');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            $table->dropColumn('strategy_label');
        });
    }
};
