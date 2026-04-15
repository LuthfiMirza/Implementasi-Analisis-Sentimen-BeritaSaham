<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            if (! Schema::hasColumn('news_articles', 'ml_sentiment_label')) {
                $table->string('ml_sentiment_label')->nullable()->after('sentiment_method');
            }
            if (! Schema::hasColumn('news_articles', 'ml_sentiment_score')) {
                $table->float('ml_sentiment_score')->nullable()->after('ml_sentiment_label');
            }
            if (! Schema::hasColumn('news_articles', 'ml_confidence')) {
                $table->float('ml_confidence')->nullable()->after('ml_sentiment_score');
            }
            if (! Schema::hasColumn('news_articles', 'ml_prob_positive')) {
                $table->float('ml_prob_positive')->nullable()->after('ml_confidence');
            }
            if (! Schema::hasColumn('news_articles', 'ml_prob_neutral')) {
                $table->float('ml_prob_neutral')->nullable()->after('ml_prob_positive');
            }
            if (! Schema::hasColumn('news_articles', 'ml_prob_negative')) {
                $table->float('ml_prob_negative')->nullable()->after('ml_prob_neutral');
            }
            if (! Schema::hasColumn('news_articles', 'rule_sentiment_label')) {
                $table->string('rule_sentiment_label')->nullable()->after('ml_prob_negative');
            }
            if (! Schema::hasColumn('news_articles', 'rule_sentiment_score')) {
                $table->float('rule_sentiment_score')->nullable()->after('rule_sentiment_label');
            }
            if (! Schema::hasColumn('news_articles', 'ml_rule_agree')) {
                $table->boolean('ml_rule_agree')->nullable()->after('rule_sentiment_score');
            }
        });
    }

    public function down(): void
    {
        Schema::table('news_articles', function (Blueprint $table) {
            foreach ([
                'ml_sentiment_label',
                'ml_sentiment_score',
                'ml_confidence',
                'ml_prob_positive',
                'ml_prob_neutral',
                'ml_prob_negative',
                'rule_sentiment_label',
                'rule_sentiment_score',
                'ml_rule_agree',
            ] as $column) {
                if (Schema::hasColumn('news_articles', $column)) {
                    $table->dropColumn($column);
                }
            }
        });
    }
};
