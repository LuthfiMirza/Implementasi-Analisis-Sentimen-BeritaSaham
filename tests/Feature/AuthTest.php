<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class AuthTest extends TestCase
{
    public function test_guest_cannot_access_dashboard(): void
    {
        // Protected dashboard data must not be visible without authentication.
        $this->get('/dashboard')->assertRedirect('/login');
    }

    public function test_login_with_valid_credentials_succeeds(): void
    {
        $user = $this->user(['password' => Hash::make('secret-password')]);

        // Valid credentials should create an authenticated session and enter the app.
        $this->post('/login', [
            'email' => $user->email,
            'password' => 'secret-password',
        ])->assertRedirect(route('dashboard', absolute: false));

        $this->assertAuthenticatedAs($user);
    }

    public function test_login_with_invalid_credentials_fails_with_validation_error(): void
    {
        $user = $this->user(['password' => Hash::make('secret-password')]);

        // Bad passwords must stay unauthenticated and report a validation failure.
        $this->from('/login')->post('/login', [
            'email' => $user->email,
            'password' => 'wrong-password',
        ])->assertRedirect('/login')->assertSessionHasErrors('email');

        $this->assertGuest();
    }

    public function test_session_uses_database_driver(): void
    {
        // Thesis audit requires persistent database sessions, not local file sessions.
        $this->assertSame('database', Config::get('session.driver'));
    }
}
