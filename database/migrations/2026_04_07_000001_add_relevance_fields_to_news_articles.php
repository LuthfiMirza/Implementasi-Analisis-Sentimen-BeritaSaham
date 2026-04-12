<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            if (! Schema::hasColumn('news_articles', 'relevance_score')) {
                $table->decimal('relevance_score', 5, 3)->nullable();
            }
            if (! Schema::hasColumn('news_articles', 'relevance_band')) {
                $table->string('relevance_band', 20)->nullable();
            }
            if (! Schema::hasColumn('news_articles', 'source_provider')) {
                $table->string('source_provider', 30)->nullable();
            }
            if (! Schema::hasColumn('news_articles', 'source_weight')) {
                $table->decimal('source_weight', 5, 2)->nullable();
            }
            if (! Schema::hasColumn('news_articles', 'matched_keywords')) {
                $table->json('matched_keywords')->nullable();
            }
        });
    }

    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->dropColumn([
                'relevance_score',
                'relevance_band',
                'source_provider',
                'source_weight',
                'matched_keywords',
            ]);
        });
    }
};
