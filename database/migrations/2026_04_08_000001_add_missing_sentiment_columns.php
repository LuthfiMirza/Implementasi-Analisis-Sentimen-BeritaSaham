<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            if (! Schema::hasColumn('news_articles', 'sentiment_confidence')) {
                $table->decimal('sentiment_confidence', 5, 2)->nullable()->after('sentiment_score');
            }
            if (! Schema::hasColumn('news_articles', 'sentiment_method')) {
                $table->string('sentiment_method', 30)->nullable()->after('sentiment_confidence');
            }
            if (! Schema::hasColumn('news_articles', 'sentiment_meta')) {
                $table->json('sentiment_meta')->nullable()->after('sentiment_method');
            }
            if (! Schema::hasColumn('news_articles', 'analyzed_at')) {
                $table->timestamp('analyzed_at')->nullable()->after('fetched_at');
            }
        });
    }

    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->dropColumn([
                'sentiment_confidence',
                'sentiment_method',
                'sentiment_meta',
                'analyzed_at',
            ]);
        });
    }
};
