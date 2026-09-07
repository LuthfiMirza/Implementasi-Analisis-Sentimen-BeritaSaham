<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::getConnection()->getDriverName() === 'mysql') {
            DB::statement("ALTER TABLE trades MODIFY result VARCHAR(32) NOT NULL DEFAULT 'open'");
        }
    }

    public function down(): void
    {
        if (Schema::getConnection()->getDriverName() === 'mysql') {
            DB::statement("ALTER TABLE trades MODIFY result ENUM('hit_target_1','hit_target_2','stop_loss','manual_close','open','trailing_stop','time_target') NOT NULL DEFAULT 'open'");
        }
    }
};
