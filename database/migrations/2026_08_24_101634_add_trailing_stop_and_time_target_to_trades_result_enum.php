<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

// Fase CZ: aturan exit strategi live (GABUNGAN/MOMENTUM/BOTTOM_REBOUND) sebenarnya ada 2 jalur
// selain hit_target_x/stop_loss/manual_close: trailing stop 2% (harga mundur >=2% dari puncak
// sejak entry) dan target waktu 10 hari bursa (Fase AL/AB-AE). Sebelumnya dua-duanya kelaparan
// jatuh ke 'manual_close' padahal beda semantik -- trailing_stop = strategi kerja normal (stop
// mengikuti peak), time_target = strategi kerja normal (durasi habis), manual_close = keputusan
// diskresi user. Bedain biar audit hasil per exit-type bisa jujur.
return new class extends Migration
{
    public function up(): void
    {
        // Sintaks ENUM/MODIFY COLUMN cuma MySQL/MariaDB -- test env pakai sqlite (in-memory)
        // yg tidak punya ENUM sebagai type; sqlite string bebas nilai apapun sudah cukup jadi
        // no-op untuk test. Prod = MySQL, produksi enum diketatkan.
        if (DB::getDriverName() !== 'mysql') {
            return;
        }
        DB::statement("ALTER TABLE trades MODIFY COLUMN result ENUM('hit_target_1', 'hit_target_2', 'stop_loss', 'manual_close', 'trailing_stop', 'time_target', 'open') NOT NULL DEFAULT 'open'");
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'mysql') {
            return;
        }
        // Turunin ulang -- baris trailing_stop/time_target di-fallback ke manual_close biar tidak
        // gagal constraint. Data lama tidak hilang (masih ada di notes/histori), cuma label enum
        // mundur.
        DB::statement("UPDATE trades SET result = 'manual_close' WHERE result IN ('trailing_stop', 'time_target')");
        DB::statement("ALTER TABLE trades MODIFY COLUMN result ENUM('hit_target_1', 'hit_target_2', 'stop_loss', 'manual_close', 'open') NOT NULL DEFAULT 'open'");
    }
};
