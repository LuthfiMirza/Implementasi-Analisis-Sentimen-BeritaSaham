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
        Schema::create('fetch_logs', function (Blueprint $table) {
            $table->id();
            $table->string('source_name');
            $table->string('status', 30);
            $table->text('message')->nullable();
            $table->unsignedInteger('records_count')->default(0);
            $table->dateTime('ran_at');
            $table->timestamps();

            $table->index(['source_name', 'status']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('fetch_logs');
    }
};
