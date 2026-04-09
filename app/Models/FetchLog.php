<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class FetchLog extends Model
{
    /** @use HasFactory<\Database\Factories\FetchLogFactory> */
    use HasFactory;

    protected $fillable = [
        'source_name',
        'status',
        'message',
        'records_count',
        'ran_at',
    ];

    protected $casts = [
        'ran_at' => 'datetime',
    ];
}
