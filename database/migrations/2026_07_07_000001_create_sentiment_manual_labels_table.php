<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sentiment_manual_labels', function (Blueprint $table) {
            $table->id();
            $table->foreignId('news_article_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->constrained();
            $table->string('label', 20);
            $table->timestamps();

            $table->unique(['news_article_id', 'user_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sentiment_manual_labels');
    }
};
