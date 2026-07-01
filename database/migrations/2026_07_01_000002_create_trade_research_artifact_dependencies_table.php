<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trade_research_artifact_dependencies', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('artifact_id');
            $table->unsignedBigInteger('depends_on_artifact_id')->nullable();
            $table->string('dependency_type', 80);
            $table->string('dependency_role', 120)->nullable();
            $table->text('expected_path')->nullable();
            $table->string('expected_artifact_type', 80)->nullable();
            $table->string('expected_schema_version', 120)->nullable();
            $table->string('expected_checksum', 128)->nullable();
            $table->text('resolved_path')->nullable();
            $table->string('resolved_checksum', 128)->nullable();
            $table->string('resolution_status', 80);
            $table->boolean('is_required')->default(true);
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->index('artifact_id', 'tr_art_dep_artifact_idx');
            $table->index('depends_on_artifact_id', 'tr_art_dep_depends_idx');
            $table->index('resolution_status', 'tr_art_dep_resolution_idx');
            $table->index('expected_checksum', 'tr_art_dep_checksum_idx');
            $table->foreign('artifact_id', 'tr_art_dep_artifact_fk')->references('id')->on('trade_research_artifacts')->cascadeOnDelete();
            $table->foreign('depends_on_artifact_id', 'tr_art_dep_depends_fk')->references('id')->on('trade_research_artifacts')->nullOnDelete();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trade_research_artifact_dependencies');
    }
};
