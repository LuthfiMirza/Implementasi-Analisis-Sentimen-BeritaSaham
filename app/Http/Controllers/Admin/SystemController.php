<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\FetchLog;
use App\Models\SystemSetting;
use Illuminate\Http\Request;

class SystemController extends Controller
{
    public function index()
    {
        $settings = SystemSetting::all()->keyBy('key');
        $fetchLogs = FetchLog::latest('ran_at')->limit(20)->get();

        return view('admin.system.index', [
            'settings' => $settings,
            'fetchLogs' => $fetchLogs,
        ]);
    }

    public function update(Request $request)
    {
        $data = $request->validate([
            'news_provider' => ['required', 'string'],
            'stock_chart_mode' => ['required', 'in:tradingview,internal'],
        ]);

        foreach ($data as $key => $value) {
            SystemSetting::updateOrCreate(['key' => $key], ['value' => ['value' => $value]]);
        }

        return back()->with('status', 'Pengaturan disimpan.');
    }
}
