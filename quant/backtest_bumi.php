<?php
require __DIR__ . '/../vendor/autoload.php';
$app = require_once __DIR__ . '/../bootstrap/app.php';
$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

use Illuminate\Support\Facades\DB;

$stockId = DB::table('stocks')->where('code', 'BUMI')->value('id');

$rows = DB::table('stock_prices')
    ->where('stock_id', $stockId)
    ->orderBy('price_date', 'asc')
    ->get()
    ->map(function ($r) {
        return [
            'date' => substr($r->price_date, 0, 10),
            'open' => (float)$r->open,
            'high' => (float)$r->high,
            'low' => (float)$r->low,
            'close' => (float)$r->close,
            'volume' => (float)$r->volume,
        ];
    })->toArray();

$n = count($rows);
echo "=== TOTAL DATA BUMI: $n hari (" . $rows[0]['date'] . " s/d " . $rows[$n - 1]['date'] . ") ===\n\n";

// Compute metrics
$closes = array_column($rows, 'close');

// Case 1: Drop >= 5% in single day
$cases_drop5 = [];
// Case 2: Drop >= 5% AND Drawdown 20d <= -20%
$cases_drawdown = [];

for ($i = 20; $i < $n - 10; $i++) {
    $prevClose = $rows[$i - 1]['close'];
    $currClose = $rows[$i]['close'];
    if ($prevClose <= 0) continue;

    $ret1d = (($currClose - $prevClose) / $prevClose) * 100;

    // rolling 20 max
    $max20 = 0;
    for ($k = $i - 19; $k <= $i; $k++) {
        if ($rows[$k]['close'] > $max20) $max20 = $rows[$k]['close'];
    }
    $dd20 = (($currClose - $max20) / $max20) * 100;

    if ($ret1d <= -5.0) {
        $nextOpen = $rows[$i + 1]['open'];
        $nextHigh = $rows[$i + 1]['high'];
        $nextLow = $rows[$i + 1]['low'];
        $nextClose = $rows[$i + 1]['close'];

        $retT1 = (($nextClose - $currClose) / $currClose) * 100;
        $highT1 = (($nextHigh - $currClose) / $currClose) * 100;
        $lowT1 = (($nextLow - $currClose) / $currClose) * 100;
        $openT1 = (($nextOpen - $currClose) / $currClose) * 100;

        $retT2 = (($rows[$i + 2]['close'] - $currClose) / $currClose) * 100;
        $retT5 = (($rows[$i + 5]['close'] - $currClose) / $currClose) * 100;
        $retT10 = (($rows[$i + 10]['close'] - $currClose) / $currClose) * 100;

        // max high in 5 days
        $maxHigh5 = 0;
        for ($h = $i + 1; $h <= $i + 5; $h++) {
            if ($rows[$h]['high'] > $maxHigh5) $maxHigh5 = $rows[$h]['high'];
        }
        $highT5 = (($maxHigh5 - $currClose) / $currClose) * 100;

        $cData = [
            'date' => $rows[$i]['date'],
            'close' => $currClose,
            'ret1d' => $ret1d,
            'dd20' => $dd20,
            'openT1' => $openT1,
            'highT1' => $highT1,
            'lowT1' => $lowT1,
            'retT1' => $retT1,
            'retT2' => $retT2,
            'retT5' => $retT5,
            'highT5' => $highT5,
            'retT10' => $retT10,
        ];

        $cases_drop5[] = $cData;
        if ($dd20 <= -20.0) {
            $cases_drawdown[] = $cData;
        }
    }
}

function summarize($name, $list) {
    $count = count($list);
    echo "===================================================================\n";
    echo "$name (Total Sampel: $count Kejadian Historis)\n";
    echo "===================================================================\n";
    if ($count == 0) return;

    $t1Green = 0;
    $t1Sum = 0;
    $t1HighSum = 0;
    $t1LowSum = 0;
    $t2Green = 0;
    $t2Sum = 0;
    $t5Green = 0;
    $t5Sum = 0;
    $t5HighSum = 0;
    $t10Green = 0;
    $t10Sum = 0;

    foreach ($list as $c) {
        if ($c['retT1'] > 0) $t1Green++;
        $t1Sum += $c['retT1'];
        $t1HighSum += $c['highT1'];
        $t1LowSum += $c['lowT1'];

        if ($c['retT2'] > 0) $t2Green++;
        $t2Sum += $c['retT2'];

        if ($c['retT5'] > 0) $t5Green++;
        $t5Sum += $c['retT5'];
        $t5HighSum += $c['highT5'];

        if ($c['retT10'] > 0) $t10Green++;
        $t10Sum += $c['retT10'];
    }

    $winT1 = ($t1Green / $count) * 100;
    $avgT1 = $t1Sum / $count;
    $avgHighT1 = $t1HighSum / $count;
    $avgLowT1 = $t1LowSum / $count;

    $winT2 = ($t2Green / $count) * 100;
    $avgT2 = $t2Sum / $count;

    $winT5 = ($t5Green / $count) * 100;
    $avgT5 = $t5Sum / $count;
    $avgHighT5 = $t5HighSum / $count;

    $winT10 = ($t10Green / $count) * 100;
    $avgT10 = $t10Sum / $count;

    echo sprintf("📌 HARI BERIKUTNYA (T+1 / BESOK):\n");
    echo sprintf("   • Win Rate Rebound (Close > Buy) : %5.1f%%\n", $winT1);
    echo sprintf("   • Rata-rata Return Close T+1     : %+5.2f%%\n", $avgT1);
    echo sprintf("   • Peluang Puncak High T+1        : %+5.2f%% (Rata-rata mantul intraday)\n", $avgHighT1);
    echo sprintf("   • Risiko Titik Terendah Low T+1  : %5.2f%% (Kedalaman gap down pagi)\n", $avgLowT1);

    echo sprintf("\n📌 HOLDING SWING 2 - 10 HARI:\n");
    echo sprintf("   • Win Rate T+2                   : %5.1f%% | Rata-rata Return: %+5.2f%%\n", $winT2, $avgT2);
    echo sprintf("   • Win Rate T+5                   : %5.1f%% | Rata-rata Return: %+5.2f%%\n", $winT5, $avgT5);
    echo sprintf("   • Rata-rata High Tertinggi 5 Hari: %+5.2f%%\n", $avgHighT5);
    echo sprintf("   • Win Rate T+10                  : %5.1f%% | Rata-rata Return: %+5.2f%%\n", $winT10, $avgT10);

    echo "\n📋 8 Kejadian Terakhir yang Mirip Kondisi Hari Ini:\n";
    $recent = array_slice($list, -8);
    echo sprintf("%-12s | %-6s | %-7s | %-7s | %-8s | %-8s | %-8s | %-8s\n", "Tanggal", "Close", "Drop 1D", "DD 20D", "High T+1", "Close T+1", "High 5D", "Close 5D");
    echo str_repeat("-", 80) . "\n";
    foreach ($recent as $r) {
        echo sprintf(
            "%-12s | Rp%-4d | %+6.1f%% | %+6.1f%% | %+7.1f%% | %+8.1f%% | %+7.1f%% | %+7.1f%%\n",
            $r['date'], $r['close'], $r['ret1d'], $r['dd20'], $r['highT1'], $r['retT1'], $r['highT5'], $r['retT5']
        );
    }
    echo "\n";
}

summarize("KASUS 1: SETIAP KALI BUMI JATUH >= 5.0% DALAM 1 HARI", $cases_drop5);
summarize("KASUS 2: BUMI JATUH >= 5.0% SAAT DRAWDOWN SUDAH >= 20% (KONDISI HARI INI)", $cases_drawdown);
