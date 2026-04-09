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
        Schema::create('stock_prices', function (Blueprint $table) {
            $table->id();
            $table->foreignId('stock_id')->constrained()->cascadeOnDelete();
            $table->dateTime('price_date');
            $table->decimal('open', 16, 2)->nullable();
            $table->decimal('high', 16, 2)->nullable();
            $table->decimal('low', 16, 2)->nullable();
            $table->decimal('close', 16, 2);
            $table->unsignedBigInteger('volume')->nullable();
            $table->string('source')->nullable();
            $table->string('interval_type', 10)->nullable();
            $table->timestamps();

            $table->index(['stock_id', 'price_date']);
            $table->index(['stock_id', 'interval_type', 'price_date']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('stock_prices');
    }
};
