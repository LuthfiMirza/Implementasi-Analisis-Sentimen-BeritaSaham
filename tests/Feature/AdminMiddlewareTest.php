<?php

namespace Tests\Feature;

use Tests\TestCase;

class AdminMiddlewareTest extends TestCase
{
    public function test_guest_cannot_access_admin_routes(): void
    {
        // Admin CRUD pages must first pass Laravel auth.
        $this->get('/admin/stocks')->assertRedirect('/login');
    }

    public function test_user_cannot_access_admin_routes(): void
    {
        // Requirement: regular users should receive 403 for admin-only URLs.
        $this->actingAsUser()->get('/admin/stocks')->assertForbidden();
    }

    public function test_admin_can_access_admin_crud_routes(): void
    {
        $this->actingAsAdmin();

        // Admin role must pass the admin middleware for CRUD entry pages.
        $this->get('/admin')->assertOk();
        $this->get('/admin/stocks')->assertOk();
        $this->get('/admin/news-sources')->assertOk();
        $this->get('/admin/news-articles')->assertOk();
    }

    public function test_role_middleware_passes_for_user_pages(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock);
        $this->seedArticle($stock);

        $this->actingAsUser();

        // User routes should require auth but not admin role.
        $this->get('/dashboard')->assertOk();
        $this->get('/news')->assertOk();
        $this->get('/watchlist')->assertOk();
    }
}
