<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('stocks', function (Blueprint $table) {
            $table->float('pbv')->nullable();
            $table->float('per')->nullable();
            $table->float('roe')->nullable();
            $table->float('der')->nullable();
            $table->float('eps')->nullable();
            $table->float('dividend_yield')->nullable();
            $table->date('fundamentals_updated_at')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('stocks', function (Blueprint $table) {
            $table->dropColumn([
                'pbv',
                'per',
                'roe',
                'der',
                'eps',
                'dividend_yield',
                'fundamentals_updated_at',
            ]);
        });
    }
};
