<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class TradeResearchArtifact extends Model
{
    protected $fillable = [
        'ticker','artifact_type','schema_version','generator_version','artifact_path','artifact_filename',
        'checksum_algorithm','checksum','file_size','generated_at','imported_at','data_start','data_end',
        'source_event_count','validation_status','usage_tier','quality_status','quality_grade',
        'usable_for_research','usable_for_decision','selected_available','warning_count',
        'critical_warning_count','informational_warning_count','warnings','limitations','summary',
        'quality_snapshot','source_snapshot','registry_notes','logical_identity','is_latest','is_stale',
        'is_quarantined','superseded_by_id',
    ];

    protected function casts(): array
    {
        return [
            'file_size' => 'integer','generated_at' => 'datetime','imported_at' => 'datetime',
            'data_start' => 'date','data_end' => 'date','source_event_count' => 'integer',
            'usable_for_research' => 'boolean','usable_for_decision' => 'boolean','selected_available' => 'boolean',
            'warning_count' => 'integer','critical_warning_count' => 'integer','informational_warning_count' => 'integer',
            'warnings' => 'array','limitations' => 'array','summary' => 'array','quality_snapshot' => 'array',
            'source_snapshot' => 'array','registry_notes' => 'array','is_latest' => 'boolean','is_stale' => 'boolean',
            'is_quarantined' => 'boolean','superseded_by_id' => 'integer',
        ];
    }

    public function dependencies(): HasMany { return $this->hasMany(TradeResearchArtifactDependency::class, 'artifact_id'); }
    public function dependents(): HasMany { return $this->hasMany(TradeResearchArtifactDependency::class, 'depends_on_artifact_id'); }
    public function supersededBy(): BelongsTo { return $this->belongsTo(self::class, 'superseded_by_id'); }
    public function supersedes(): HasMany { return $this->hasMany(self::class, 'superseded_by_id'); }

    public function scopeForTicker(Builder $query, string $ticker): Builder { return $query->where('ticker', strtoupper($ticker)); }
    public function scopeOfType(Builder $query, string $type): Builder { return $query->where('artifact_type', $type); }
    public function scopeLatest(Builder $query): Builder { return $query->where('is_latest', true); }
    public function scopeValid(Builder $query): Builder { return $query->where('validation_status', 'valid'); }
    public function scopeResearchUsable(Builder $query): Builder { return $query->where('usable_for_research', true); }
    public function scopeDecisionUsable(Builder $query): Builder { return $query->where('usable_for_decision', true)->where('selected_available', true); }
    public function scopeNotStale(Builder $query): Builder { return $query->where('is_stale', false); }
    public function scopeNotQuarantined(Builder $query): Builder { return $query->where('is_quarantined', false); }
    public function scopeHistory(Builder $query): Builder { return $query->orderByDesc('generated_at')->orderByDesc('id'); }
}
