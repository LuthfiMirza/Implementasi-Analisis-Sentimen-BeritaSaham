<?php

namespace App\Http\Controllers;

use App\Models\Trade;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Throwable;

class HealthController extends Controller
{
    /**
     * Endpoint Healthcheck: memeriksa kondisi database, servis Python ML,
     * dan scheduler sistem Sentimena.
     */
    public function index(): JsonResponse
    {
        $services = [];
        $overallHealthy = true;

        // 1. Cek Koneksi Database
        try {
            DB::connection()->getPdo();
            $openTrades = Trade::where('status', 'open')->count();
            $closedTrades = Trade::where('status', 'closed')->count();
            $services['database'] = [
                'status' => 'ok',
                'open_trades' => $openTrades,
                'closed_trades' => $closedTrades,
            ];
        } catch (Throwable $e) {
            $overallHealthy = false;
            $services['database'] = [
                'status' => 'down',
                'error' => $e->getMessage(),
            ];
        }

        // 2. Cek Sentiment API (8002)
        try {
            $resp = Http::timeout(1.5)->get('http://127.0.0.1:8002/docs');
            $services['sentiment_api'] = [
                'status' => $resp->ok() ? 'ok' : 'degraded',
                'port' => 8002,
                'http_code' => $resp->status(),
            ];
            if (! $resp->ok()) {
                $overallHealthy = false;
            }
        } catch (Throwable) {
            $services['sentiment_api'] = [
                'status' => 'down',
                'port' => 8002,
            ];
            $overallHealthy = false;
        }

        // 3. Cek Prediction API (8001)
        try {
            $resp = Http::timeout(1.5)->get('http://127.0.0.1:8001/docs');
            $services['prediction_api'] = [
                'status' => $resp->ok() ? 'ok' : 'degraded',
                'port' => 8001,
                'http_code' => $resp->status(),
            ];
            if (! $resp->ok()) {
                $overallHealthy = false;
            }
        } catch (Throwable) {
            $services['prediction_api'] = [
                'status' => 'down',
                'port' => 8001,
            ];
            $overallHealthy = false;
        }

        // 4. Cek Scheduler / Cron Process
        $schedulerPid = exec("pgrep -f 'artisan schedule:work'");
        $services['scheduler'] = [
            'status' => ! empty($schedulerPid) ? 'ok' : 'inactive',
            'pid' => ! empty($schedulerPid) ? (int) $schedulerPid : null,
        ];
        if (empty($schedulerPid)) {
            $overallHealthy = false;
        }

        $statusCode = $overallHealthy ? 200 : 207;

        return response()->json([
            'status' => $overallHealthy ? 'healthy' : 'degraded',
            'timestamp' => now()->timezone('Asia/Jakarta')->toIso8601String(),
            'services' => $services,
            'summary' => $overallHealthy
                ? 'All 5 Sentimena services operational.'
                : 'One or more services need attention.',
        ], $statusCode);
    }
}

