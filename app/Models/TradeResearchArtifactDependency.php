<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TradeResearchArtifactDependency extends Model
{
    protected $fillable = [
        'artifact_id','depends_on_artifact_id','dependency_type','dependency_role','expected_path',
        'expected_artifact_type','expected_schema_version','expected_checksum','resolved_path','resolved_checksum',
        'resolution_status','is_required','metadata',
    ];

    protected function casts(): array
    {
        return ['artifact_id'=>'integer','depends_on_artifact_id'=>'integer','is_required'=>'boolean','metadata'=>'array'];
    }

    public function artifact(): BelongsTo { return $this->belongsTo(TradeResearchArtifact::class, 'artifact_id'); }
    public function dependsOnArtifact(): BelongsTo { return $this->belongsTo(TradeResearchArtifact::class, 'depends_on_artifact_id'); }
}
