<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            if (! Schema::hasColumn('news_articles', 'detected_language')) {
                $table->string('detected_language', 10)->nullable()->after('language');
            }
            if (! Schema::hasColumn('news_articles', 'entity_match_score')) {
                $table->decimal('entity_match_score', 5, 3)->nullable()->after('relevance_score');
            }
            if (! Schema::hasColumn('news_articles', 'market_context_score')) {
                $table->decimal('market_context_score', 5, 3)->nullable()->after('entity_match_score');
            }
            if (! Schema::hasColumn('news_articles', 'language_score')) {
                $table->decimal('language_score', 5, 3)->nullable()->after('market_context_score');
            }
            if (! Schema::hasColumn('news_articles', 'final_quality_score')) {
                $table->decimal('final_quality_score', 5, 3)->nullable()->after('language_score')->index();
            }
            if (! Schema::hasColumn('news_articles', 'quality_band')) {
                $table->string('quality_band', 20)->nullable()->after('relevance_band');
            }
            if (! Schema::hasColumn('news_articles', 'quality_flags')) {
                $table->json('quality_flags')->nullable()->after('matched_keywords');
            }
        });
    }

    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->dropColumn([
                'detected_language',
                'entity_match_score',
                'market_context_score',
                'language_score',
                'final_quality_score',
                'quality_band',
                'quality_flags',
            ]);
        });
    }
};
