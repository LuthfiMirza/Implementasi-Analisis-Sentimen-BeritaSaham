<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->string('ml_sentiment_label')->nullable()->after('sentiment_method');
            $table->float('ml_sentiment_score')->nullable()->after('ml_sentiment_label');
            $table->float('ml_confidence')->nullable()->after('ml_sentiment_score');
            $table->string('rule_sentiment_label')->nullable()->after('ml_confidence');
            $table->float('rule_sentiment_score')->nullable()->after('rule_sentiment_label');
            $table->boolean('ml_rule_agree')->nullable()->after('rule_sentiment_score');
        });
    }

    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            $table->dropColumn([
                'ml_sentiment_label',
                'ml_sentiment_score',
                'ml_confidence',
                'rule_sentiment_label',
                'rule_sentiment_score',
                'ml_rule_agree',
            ]);
        });
    }
};
