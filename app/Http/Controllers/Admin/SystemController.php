<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\FetchLog;
use App\Models\SystemSetting;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Artisan;

class SystemController extends Controller
{
    /**
     * One-click manual triggers shown on the admin system page. Allow-listed only -- the web
     * request never passes free-form input to Artisan.
     *
     * @var array<string, array{command: string, params: array<string, mixed>, label: string, note: string}>
     */
    public const TASKS = [
        'idx_fetch' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => [],
            'label' => 'Ambil data IDX hari ini',
            'note' => 'Ringkasan saham EOD (volume, gap, arus asing). Jalankan setelah ~18:05 WIB.',
        ],
        'idx_recover' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => ['--recover' => true],
            'label' => 'Tambal hari bursa yang hilang',
            'note' => 'Cek 5 hari bursa terakhir, ambil yang belum masuk. Aman diklik kapan saja.',
        ],
        'idx_backfill' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => ['--backfill' => 10],
            'label' => 'Backfill 10 hari IDX',
            'note' => 'Isi mundur ~10 hari bursa. Perlu beberapa puluh detik.',
        ],
        // NB: news:fetch sengaja TIDAK di sini -- 10-30+ menit menembak banyak feed eksternal
        // lambat, dan `set_time_limit` tidak menolong (waktunya di I/O wait, bukan CPU) -- sempat
        // membekukan `php artisan serve`. News sudah dijadwalkan 5x/hari + auto-recover 30 menit;
        // untuk manual pakai terminal: `php artisan news:fetch`.
    ];

    public function index()
    {
        $settings = SystemSetting::all()->keyBy('key');
        $fetchLogs = FetchLog::latest('ran_at')->limit(20)->get();

        return view('admin.system.index', [
            'settings' => $settings,
            'fetchLogs' => $fetchLogs,
            'tasks' => self::TASKS,
        ]);
    }

    public function runTask(Request $request)
    {
        $key = (string) $request->input('task');
        $task = self::TASKS[$key] ?? null;

        if ($task === null) {
            return back()->with('status', "Task tidak dikenal: {$key}");
        }

        @set_time_limit(180);

        try {
            $exit = Artisan::call($task['command'], $task['params']);
            $output = trim(Artisan::output());
        } catch (\Throwable $e) {
            return back()->with('status', "❌ {$task['label']} error: ".$e->getMessage());
        }

        $tail = collect(explode("\n", $output))->filter()->slice(-4)->implode(' | ');
        $status = ($exit === 0 ? '✅' : '⚠️')." {$task['label']}".($tail !== '' ? " — {$tail}" : '');

        return back()->with('status', $status);
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
