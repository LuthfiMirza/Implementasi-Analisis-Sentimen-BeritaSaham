<?php

namespace Tests\Feature;

use App\Http\Controllers\Admin\SystemController;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class AdminSystemRunTaskTest extends TestCase
{
    public function test_regular_user_cannot_run_tasks(): void
    {
        $this->actingAsUser()
            ->post('/admin/system/run', ['task' => 'idx_recover'])
            ->assertForbidden();
    }

    public function test_admin_runs_an_allowlisted_task_and_sees_status(): void
    {
        Artisan::shouldReceive('call')->once()
            ->with('idx:fetch-daily-summary', ['--recover' => true])
            ->andReturn(0);
        Artisan::shouldReceive('output')->andReturn("Semua 5 hari bursa terakhir sudah lengkap.\n");

        $this->actingAsAdmin()
            ->post('/admin/system/run', ['task' => 'idx_recover'])
            ->assertRedirect();

        $this->assertStringContainsString('sudah lengkap', session('status'));
        $this->assertStringContainsString('✅', session('status'));
    }

    public function test_unknown_task_is_rejected_without_calling_artisan(): void
    {
        Artisan::shouldReceive('call')->never();

        $this->actingAsAdmin()
            ->post('/admin/system/run', ['task' => 'rm -rf /'])
            ->assertRedirect();

        $this->assertStringContainsString('tidak dikenal', session('status'));
    }

    public function test_every_allowlisted_task_points_at_a_registered_command(): void
    {
        $registered = array_keys(Artisan::all());

        foreach (SystemController::TASKS as $key => $task) {
            $this->assertContains(
                $task['command'],
                $registered,
                "Task '{$key}' menunjuk ke command yang tidak terdaftar: {$task['command']}"
            );
            $this->assertArrayHasKey('label', $task);
            $this->assertArrayHasKey('note', $task);
            $this->assertArrayHasKey('group', $task);
        }
    }
}
