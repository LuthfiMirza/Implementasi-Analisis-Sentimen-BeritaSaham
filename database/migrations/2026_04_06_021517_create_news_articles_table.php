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
        Schema::create('news_articles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('stock_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('news_source_id')->nullable()->constrained()->nullOnDelete();
            $table->string('title');
            $table->string('slug')->unique();
            $table->string('source_url')->unique();
            $table->timestamp('published_at')->nullable();
            $table->text('summary')->nullable();
            $table->text('content_snippet')->nullable();
            $table->longText('full_text')->nullable();
            $table->string('sentiment_label', 20)->nullable();
            $table->decimal('sentiment_score', 5, 2)->nullable();
            $table->decimal('sentiment_confidence', 5, 2)->nullable();
            $table->string('sentiment_method', 30)->nullable();
            $table->json('sentiment_meta')->nullable();
            $table->string('language', 5)->default('id');
            $table->longText('raw_payload')->nullable();
            $table->timestamp('fetched_at')->nullable();
            $table->timestamp('analyzed_at')->nullable();
            $table->timestamps();

            $table->index('stock_id');
            $table->index('published_at');
            $table->index('sentiment_label');
            $table->index('sentiment_method');
            $table->index('analyzed_at');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('news_articles');
    }
};
