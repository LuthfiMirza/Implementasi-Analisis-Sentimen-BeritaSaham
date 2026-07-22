<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('sentiment_manual_labels', function (Blueprint $table) {
            if (! Schema::hasColumn('sentiment_manual_labels', 'sample_method')) {
                $table->string('sample_method', 40)->nullable()->after('label')->index();
            }
        });

        DB::table('sentiment_manual_labels')
            ->whereNull('sample_method')
            ->update(['sample_method' => 'legacy_hard_case']);
    }

    public function down(): void
    {
        Schema::table('sentiment_manual_labels', function (Blueprint $table) {
            if (Schema::hasColumn('sentiment_manual_labels', 'sample_method')) {
                $table->dropIndex(['sample_method']);
                $table->dropColumn('sample_method');
            }
        });
    }
};
