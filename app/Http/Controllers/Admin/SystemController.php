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
     * request never passes free-form input to Artisan. Every task here must finish in seconds
     * to low tens of seconds (synchronous web request).
     *
     * Deliberately excluded:
     *  - `news:fetch*` -- 10-30+ min hammering slow external feeds, froze `php artisan serve`.
     *  - `prediction:refresh-price-history` / `prediction:retrain-*` -- minutes of ML work.
     *  - `research:detect-drawdown-bounce-signal` & friends -- fire Telegram alerts (side effects).
     * For those, use the terminal.
     *
     * @var array<string, array{command: string, params: array<string, mixed>, label: string, note: string, group: string}>
     */
    public const TASKS = [
        // ── Market Alerts / IDX ──────────────────────────────────────────────
        'idx_fetch' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => [],
            'label' => 'Ambil data IDX hari ini',
            'note' => 'Ringkasan saham EOD (volume, gap, arus asing). Jalankan setelah ~18:05 WIB.',
            'group' => 'Market Alerts / IDX',
        ],
        'idx_recover' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => ['--recover' => true],
            'label' => 'Tambal hari bursa IDX yang hilang',
            'note' => 'Cek 5 hari bursa terakhir, ambil yang belum masuk. Aman diklik kapan saja.',
            'group' => 'Market Alerts / IDX',
        ],
        'idx_backfill' => [
            'command' => 'idx:fetch-daily-summary',
            'params' => ['--backfill' => 10],
            'label' => 'Backfill 10 hari IDX',
            'note' => 'Isi mundur ~10 hari bursa. Perlu beberapa puluh detik.',
            'group' => 'Market Alerts / IDX',
        ],
        'foreign_flow_snapshot' => [
            'command' => 'research:collect-foreign-flow',
            'params' => [],
            'label' => 'Snapshot arus asing (infovesta)',
            'note' => 'Top-5 net beli/jual asing hari ini ke log riset. ~4 detik.',
            'group' => 'Market Alerts / IDX',
        ],

        // ── Harga & fundamental ──────────────────────────────────────────────
        'sync_live' => [
            'command' => 'stocks:sync-live',
            'params' => ['--all-active' => true],
            'label' => 'Sync harga live',
            'note' => 'Tarik harga terkini semua saham aktif (Yahoo). ~1 detik.',
            'group' => 'Harga & fundamental',
        ],
        'fetch_history' => [
            'command' => 'stocks:fetch-history',
            'params' => ['--days' => 1],
            'label' => 'Ambil harga penutupan harian',
            'note' => 'Snapshot OHLCV harian (dipakai indikator & prediksi). ~2 detik.',
            'group' => 'Harga & fundamental',
        ],
        'sync_fundamentals' => [
            'command' => 'stocks:sync-fundamentals',
            'params' => [],
            'label' => 'Sync fundamental (PBV/PER/ROE)',
            'note' => 'Rasio fundamental per saham. Jadwal mingguan. ~15 detik.',
            'group' => 'Harga & fundamental',
        ],
    ];

    public function index()
    {
        $settings = SystemSetting::all()->keyBy('key');
        $fetchLogs = FetchLog::latest('ran_at')->limit(20)->get();

        return view('admin.system.index', [
            'settings' => $settings,
            'fetchLogs' => $fetchLogs,
            'taskGroups' => collect(self::TASKS)
                ->map(fn (array $t, string $key): array => $t + ['key' => $key])
                ->groupBy('group'),
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
