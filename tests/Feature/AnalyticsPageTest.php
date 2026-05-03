<?php

namespace Tests\Feature;

use Tests\TestCase;

class AnalyticsPageTest extends TestCase
{
    public function test_analytics_page_returns_200_for_authenticated_user(): void
    {
        $stock = $this->seedStock('BBCA');
        $this->seedPriceSeries($stock, 60);
        $this->seedArticle($stock);

        // Authenticated users should be able to inspect thesis analytics.
        $this->actingAsUser()->get('/analytics?code=BBCA&period=30')->assertOk();
    }

    public function test_analytics_page_redirects_for_guest(): void
    {
        // Analytics contains account context and should be protected.
        $this->get('/analytics?code=BBCA&period=30')->assertRedirect('/login');
    }
}
