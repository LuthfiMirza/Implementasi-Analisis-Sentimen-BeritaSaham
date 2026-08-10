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
        // 768 -- batas aman index UNIQUE utf8mb4 (768 * 4 byte = 3072 byte, limit InnoDB/MariaDB
        // default). Link asli Google News RSS panjangnya 196-873 karakter (dicek langsung dari
        // raw_payload tersimpan); kolom lama varchar(255) dan kode fallback-nya truncate di 240
        // karakter membuat SEMUA link >240 karakter diganti hash palsu yang tidak pernah valid
        // (404/400 Google). 768 mencakup mayoritas kasus nyata, sisanya (>768) tetap fallback ke
        // hash (Fase BI).
        Schema::table('news_articles', function (Blueprint $table) {
            $table->string('source_url', 768)->change();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->string('source_url', 255)->change();
        });
    }
};
