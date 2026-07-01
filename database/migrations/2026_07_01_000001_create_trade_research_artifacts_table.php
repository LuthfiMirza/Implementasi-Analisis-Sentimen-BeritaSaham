<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trade_research_artifacts', function (Blueprint $table) {
            $table->id();
            $table->string('ticker', 16);
            $table->string('artifact_type', 80);
            $table->string('schema_version', 120);
            $table->string('generator_version', 120)->nullable();
            $table->text('artifact_path');
            $table->string('artifact_filename');
            $table->string('checksum_algorithm', 32);
            $table->string('checksum', 128);
            $table->unsignedBigInteger('file_size');
            $table->timestamp('generated_at')->nullable();
            $table->timestamp('imported_at')->nullable();
            $table->date('data_start')->nullable();
            $table->date('data_end')->nullable();
            $table->unsignedInteger('source_event_count')->nullable();
            $table->string('validation_status', 80);
            $table->string('usage_tier', 80)->default('none');
            $table->string('quality_status', 120)->nullable();
            $table->string('quality_grade', 80)->nullable();
            $table->boolean('usable_for_research')->default(false);
            $table->boolean('usable_for_decision')->default(false);
            $table->boolean('selected_available')->default(false);
            $table->unsignedInteger('warning_count')->default(0);
            $table->unsignedInteger('critical_warning_count')->default(0);
            $table->unsignedInteger('informational_warning_count')->default(0);
            $table->json('warnings')->nullable();
            $table->json('limitations')->nullable();
            $table->json('summary')->nullable();
            $table->json('quality_snapshot')->nullable();
            $table->json('source_snapshot')->nullable();
            $table->json('registry_notes')->nullable();
            $table->string('logical_identity', 255);
            $table->boolean('is_latest')->default(false);
            $table->boolean('is_stale')->default(false);
            $table->boolean('is_quarantined')->default(false);
            $table->foreignId('superseded_by_id')->nullable()->constrained('trade_research_artifacts')->nullOnDelete();
            $table->timestamps();

            $table->index(['ticker', 'artifact_type']);
            $table->index(['ticker', 'artifact_type', 'is_latest']);
            $table->index(['ticker', 'artifact_type', 'usage_tier']);
            $table->index('validation_status');
            $table->index('usage_tier');
            $table->index('checksum');
            $table->index('logical_identity');
            $table->index('generated_at');
            $table->index('is_stale');
            $table->index('is_quarantined');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trade_research_artifacts');
    }
};
