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
        Schema::create('stocks', function (Blueprint $table) {
            $table->id();
            $table->string('code', 10)->unique();
            $table->string('company_name');
            $table->string('sector')->nullable();
            $table->text('description')->nullable();
            $table->string('exchange')->default('IDX');
            $table->string('tradingview_symbol')->nullable();
            $table->string('yahoo_symbol')->nullable();
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('stocks');
    }
};
