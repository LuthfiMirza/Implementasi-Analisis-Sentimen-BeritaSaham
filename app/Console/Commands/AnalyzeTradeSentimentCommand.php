<?php

namespace App\Console\Commands;

use App\Models\NewsArticle;
use App\Models\Trade;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;

/**
 * Menempelkan skor sentimen berita harian ke tiap entri trade journal (mis. hasil
 * php artisan sim:load-trades) supaya bisa dikaji: apakah entry yang berbarengan
 * dengan sentimen negatif memang lebih sering berakhir stop-loss. Ini analisis
 * deskriptif untuk bahan diskusi dengan dosen pembimbing, bukan validasi statistik
 * formal (N terlalu kecil untuk uji signifikansi).
 */
class AnalyzeTradeSentimentCommand extends Command
{
    protected $signature = 'trades:analyze-sentiment {--user=2} {--window=5 : Hari ke belakang dari entry_date untuk rata-rata sentimen}';

    protected $description = 'Tempelkan skor sentimen harian ke tiap trade journal dan ringkas korelasinya dengan hasil trade.';

    public function handle(): int
    {
        $userId = (int) $this->option('user');
        $window = (int) $this->option('window');

        $trades = Trade::with('stock')->where('user_id', $userId)->orderBy('entry_date')->get();

        if ($trades->isEmpty()) {
            $this->error('Tidak ada trade untuk user ini.');

            return self::FAILURE;
        }

        $rows = [];
        foreach ($trades as $t) {
            $start = Carbon::parse($t->entry_date)->copy()->subDays($window);
            $end = Carbon::parse($t->entry_date)->copy()->subDay();

            $articles = NewsArticle::where('stock_id', $t->stock_id)
                ->whereBetween('published_at', [$start->startOfDay(), $end->endOfDay()])
                ->whereNotNull('sentiment_score')
                ->get(['sentiment_score', 'sentiment_label']);

            $avgSentiment = $articles->count() > 0 ? round($articles->avg('sentiment_score'), 3) : null;
            $negCount = $articles->where('sentiment_label', 'negative')->count();
            $posCount = $articles->where('sentiment_label', 'positive')->count();

            $rows[] = [
                'ticker' => $t->ticker ?: $t->stock->code,
                'entry_date' => Carbon::parse($t->entry_date)->toDateString(),
                'result' => $t->result,
                'pnl_percent' => $t->pnl_percent,
                'n_articles' => $articles->count(),
                'avg_sentiment' => $avgSentiment,
                'neg' => $negCount,
                'pos' => $posCount,
            ];
        }

        $this->table(
            ['Ticker', 'Entry', 'Hasil', 'PnL%', '#Berita', 'Avg Sentimen', 'Neg', 'Pos'],
            $rows
        );

        $wins = collect($rows)->whereIn('result', ['hit_target_1', 'hit_target_2']);
        $losses = collect($rows)->where('result', 'stop_loss');

        $winsWithSentiment = $wins->whereNotNull('avg_sentiment');
        $lossesWithSentiment = $losses->whereNotNull('avg_sentiment');

        $avgSentimentWins = $winsWithSentiment->avg('avg_sentiment');
        $avgSentimentLosses = $lossesWithSentiment->avg('avg_sentiment');

        $this->newLine();
        $this->info('=== RINGKASAN (deskriptif, N kecil -- bukan uji signifikansi) ===');
        $this->line("Trade menang (TP): {$wins->count()} | ada data sentimen: {$winsWithSentiment->count()}");
        $this->line('Rata-rata sentimen '.$window.' hari sebelum entry (menang): '.
            ($avgSentimentWins !== null ? round($avgSentimentWins, 3) : 'n/a (tidak ada berita)'));
        $this->line("Trade kalah (SL): {$losses->count()} | ada data sentimen: {$lossesWithSentiment->count()}");
        $this->line('Rata-rata sentimen '.$window.' hari sebelum entry (kalah): '.
            ($avgSentimentLosses !== null ? round($avgSentimentLosses, 3) : 'n/a (tidak ada berita)'));

        if ($avgSentimentWins !== null && $avgSentimentLosses !== null) {
            $delta = round($avgSentimentWins - $avgSentimentLosses, 3);
            $this->line("Selisih (menang - kalah): {$delta}");
        }

        $noNews = collect($rows)->where('n_articles', 0)->count();
        $this->newLine();
        $this->comment("Catatan: {$noNews} dari ".count($rows)." trade tidak punya berita sama sekali di window {$window} hari sebelum entry -- coverage berita BUMI/DEWA memang rendah (lihat Gap 1), jadi kesimpulan harus dibaca sebagai indikasi awal, bukan bukti kuat.");

        return self::SUCCESS;
    }
}
