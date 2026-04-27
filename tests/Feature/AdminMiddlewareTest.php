<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AdminMiddlewareTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_user_can_access_admin_dashboard(): void
    {
        $admin = User::factory()->admin()->create();

        $response = $this->actingAs($admin)->get('/admin');

        $response->assertOk();
        $response->assertSeeText('Pengaturan Sistem');
    }

    public function test_regular_user_is_redirected_from_admin_dashboard(): void
    {
        $user = User::factory()->create(['role' => 'user']);

        $response = $this->actingAs($user)->get('/admin');

        $response->assertRedirect(route('dashboard'));
    }

    public function test_guest_is_redirected_to_login_from_admin_dashboard(): void
    {
        $response = $this->get('/admin');

        $response->assertRedirect(route('login'));
    }
}
