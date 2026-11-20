<?php

namespace App\Services\News;

use App\Models\Stock;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class NewsEventClassifierService
{
    /**
     * Tickers whose symbols match common Indonesian/English everyday words
     * and therefore strictly require capital-market context keywords.
     *
     * @var list<string>
     */
    private const AMBIGUOUS_TICKERS = [
        'WIFI', 'IDEA', 'IKAN', 'PACK', 'FAST', 'AUTO', 'MINA', 'GULA',
        'BAIK', 'BULL', 'COCO', 'COIN', 'RANS', 'EMAS', 'DOOH', 'PADA',
        'PADI', 'KOTA', 'JELI', 'RATU', 'RAJA', 'SINI', 'BUMI', 'DEWA',
    ];

    /** @var list<string> */
    private const MARKET_CONTEXT_KEYWORDS = [
        'saham', 'emiten', 'tbk', 'bei', 'idx', 'ihsg', 'bursa', 'sekuritas',
        'investor', 'dividen', 'buyback', 'rups', 'rupslb', 'right issue',
        'laba', 'rugi', 'pendapatan', 'kinerja keuangan', 'laporan keuangan',
        'triliun', 'miliar', 'rupiah', 'us$', 'usd', 'akuisisi', 'inbreng',
        'pengendali', 'komisaris', 'direksi', 'suspensi', 'uma', 'fca',
        'delisting', 'pailit', 'pkpu', 'impairment', 'obligasi', 'ekspansi',
        'tambang', 'nikel', 'timah', 'batu bara', 'batubara', 'migas', 'minyak',
        'geotermal', 'infrastruktur', 'teknikal', 'analis', 'rekomendasi',
        'top loser', 'top gainer', 'arb', 'ara', 'corporate action', 'depository',
    ];

    /** @var list<string> */
    private const SUSPENSION_PATTERNS = [
        'suspensi', 'disuspensi', 'penghentian sementara', 'unusual market activity',
        '\buma\b', 'full call auction', '\bfca\b', 'papan pemantauan khusus',
        'delisting', 'pailit', '\bpkpu\b', 'gagal bayar', 'default utang',
    ];

    /** @var list<string> */
    private const HARD_RISK_PATTERNS = [
        'laba.*anjlok', 'laba.*turun', 'laba.*merosot', 'laba.*terjun', 'laba.*susut',
        'rugi bersih', 'cetak rugi', 'mencatat rugi', 'impairment',
        'pengendali.*jual', 'jual.*saham pengendali', 'lepas.*saham', 'investor lepas',
        'mundur dari komisaris', 'mundur dari direksi', 'right issue.*pangkas',
        'tersangka', 'korupsi', 'digugat', 'gugatan', 'denda ojk', 'wacana.*70%',
        'tutupan sementara', 'tutup sementara',
    ];

    /** @var list<string> */
    private const CATALYST_PATTERNS = [
        'buyback', 'pembelian kembali saham', 'dividen', 'akuisisi',
        'investor strategis', 'laba.*naik', 'laba.*melonjak', 'laba.*tumbuh',
        'bukukan laba', 'cetak laba', 'kontrak baru', 'sumber minyak',
        'temukan.*minyak', 'temukan.*cadangan', 'inbreng', 'suntikan dana',
        'depository receipts', 'harga premium', 'duet.*tambang', 'investasi.*miliar',
        'investasi.*triliun', 'ekspansi', 'melesat', 'batas atas',
    ];

    /** @var list<string> */
    private const PANIC_DROP_PATTERNS = [
        'top loser', 'anjlok', 'terkoreksi', 'melemah', 'merosot', 'ambrol',
        'turun tajam', 'koreksi tajam', 'zona merah', 'tertekan',
    ];

    /**
     * Check whether an article is genuinely finance/stock-market relevant.
     */
    public function isFinanciallyRelevant(string $title, ?string $ticker = null, ?string $summary = null): bool
    {
        $text = mb_strtolower(trim($title . ' ' . ($summary ?? '')));
        if ($text === '' || mb_strlen(trim($title)) < 18) {
            return false;
        }

        // Explicit spam / lifestyle false-positive blockers
        $noiseBlockers = [
            'nama wifi lucu', 'password yang buat ketawa', 'budidaya ikan darat',
            'budi daya ikan', 'flash sale dan countdown', 'dark patterns',
            'resep ', 'cara memasak', 'lirik lagu', 'jadwal sholat', 'ramalan zodiak',
        ];
        foreach ($noiseBlockers as $noise) {
            if (str_contains($text, $noise)) {
                return false;
            }
        }

        $hasContext = false;
        foreach (self::MARKET_CONTEXT_KEYWORDS as $kw) {
            if (str_contains($text, $kw)) {
                $hasContext = true;
                break;
            }
        }

        $upperTicker = strtoupper((string) $ticker);
        if ($upperTicker !== '' && in_array($upperTicker, self::AMBIGUOUS_TICKERS, true)) {
            return $hasContext;
        }

        return $hasContext || mb_strlen(trim($title)) >= 30;
    }

    /**
     * Classify a single news title (+ optional summary & ML sentiment) into 1 of 5 actionable event tags.
     *
     * @return array{tag: string, label: string, severity: int, matched: ?string}
     */
    public function classifyArticle(string $title, ?string $summary = null, ?string $sentimentLabel = null, ?float $sentimentScore = null): array
    {
        $text = mb_strtolower(trim($title . ' ' . ($summary ?? '')));

        foreach (self::SUSPENSION_PATTERNS as $pat) {
            if (preg_match('/' . $pat . '/iu', $text)) {
                return ['tag' => 'SUSPENSION_ALERT', 'label' => '⛔ SUSPENSI / UMA', 'severity' => 4, 'matched' => $pat];
            }
        }

        foreach (self::HARD_RISK_PATTERNS as $pat) {
            if (preg_match('/' . $pat . '/iu', $text)) {
                return ['tag' => 'HARD_RISK', 'label' => '🔴 HARD RISK', 'severity' => 3, 'matched' => $pat];
            }
        }

        foreach (self::CATALYST_PATTERNS as $pat) {
            if (preg_match('/' . $pat . '/iu', $text)) {
                return ['tag' => 'CATALYST', 'label' => '🟢 CATALYST', 'severity' => 2, 'matched' => $pat];
            }
        }

        foreach (self::PANIC_DROP_PATTERNS as $pat) {
            if (preg_match('/' . $pat . '/iu', $text)) {
                return ['tag' => 'PANIC_DROP', 'label' => '🟡 PANIC DROP', 'severity' => 1, 'matched' => $pat];
            }
        }

        // Fallback to ML sentiment when strongly confident
        if ($sentimentLabel === 'negative' && ($sentimentScore ?? 0) <= -0.5) {
            return ['tag' => 'HARD_RISK', 'label' => '🔴 NEGATIVE', 'severity' => 3, 'matched' => 'ml_negative'];
        }
        if ($sentimentLabel === 'positive' && ($sentimentScore ?? 0) >= 0.5) {
            return ['tag' => 'CATALYST', 'label' => '🟢 POSITIVE', 'severity' => 2, 'matched' => 'ml_positive'];
        }

        return ['tag' => 'NEUTRAL', 'label' => '⚪ NEUTRAL', 'severity' => 0, 'matched' => null];
    }

    /**
     * Batch-summarize relevant news events for multiple tickers in a single query.
     *
     * @param  list<string>  $tickers
     * @return array<string, array<string, mixed>>
     */
    public function summarizeBatch(array $tickers, int $days = 14): array
    {
        $cleanTickers = array_values(array_unique(array_filter(array_map(
            fn ($t) => strtoupper(trim((string) $t)),
            $tickers
        ))));

        $emptyDefault = fn () => [
            'badge' => 'NONE',
            'label' => 'Tidak Ada Katalis',
            'badge_class' => 'bg-slate-800/70 text-slate-400 border-slate-700/70',
            'headline' => null,
            'published_at' => null,
            'counts' => [
                'total_relevant' => 0,
                'filtered_noise' => 0,
                'suspension' => 0,
                'hard_risk' => 0,
                'catalyst' => 0,
                'panic_drop' => 0,
            ],
            'events' => [],
        ];

        $result = [];
        foreach ($cleanTickers as $t) {
            $result[$t] = $emptyDefault();
        }

        if (empty($cleanTickers) || ! Schema::hasTable('news_articles') || ! Schema::hasTable('stocks')) {
            return $result;
        }

        $stocks = Stock::whereIn('code', $cleanTickers)->get(['id', 'code']);
        if ($stocks->isEmpty()) {
            return $result;
        }

        $idToCode = $stocks->pluck('code', 'id')->map(fn ($c) => strtoupper((string) $c))->all();
        $since = now('Asia/Jakarta')->subDays($days)->startOfDay()->format('Y-m-d H:i:s');

        $articles = DB::table('news_articles')
            ->whereIn('stock_id', array_keys($idToCode))
            ->where('published_at', '>=', $since)
            ->orderByDesc('published_at')
            ->get(['id', 'stock_id', 'title', 'summary', 'source_url', 'sentiment_label', 'sentiment_score', 'published_at']);

        $grouped = [];
        foreach ($articles as $art) {
            $code = $idToCode[$art->stock_id] ?? null;
            if (! $code) {
                continue;
            }
            $grouped[$code][] = $art;
        }

        foreach ($grouped as $code => $rows) {
            $result[$code] = $this->buildSummaryFromRows($code, $rows);
        }

        return $result;
    }

    /**
     * Build event summary + dated events for a single ticker (used on /trades/{id}).
     *
     * @return array<string, mixed>
     */
    public function summarizeForTicker(string $ticker, int $days = 30, ?string $untilDate = null): array
    {
        $code = strtoupper(trim($ticker));
        if (! Schema::hasTable('news_articles') || ! Schema::hasTable('stocks')) {
            return $this->summarizeBatch([$code], $days)[$code];
        }

        $stock = Stock::where('code', $code)->first(['id', 'code']);
        if (! $stock) {
            return $this->summarizeBatch([$code], $days)[$code];
        }

        $end = $untilDate ? Carbon::parse($untilDate, 'Asia/Jakarta')->endOfDay() : now('Asia/Jakarta');
        $start = $end->copy()->subDays($days)->startOfDay();

        $rows = DB::table('news_articles')
            ->where('stock_id', $stock->id)
            ->whereBetween('published_at', [$start->format('Y-m-d H:i:s'), $end->format('Y-m-d H:i:s')])
            ->orderByDesc('published_at')
            ->limit(40)
            ->get(['id', 'stock_id', 'title', 'summary', 'source_url', 'sentiment_label', 'sentiment_score', 'published_at'])
            ->all();

        return $this->buildSummaryFromRows($code, $rows);
    }

    /**
     * @param  list<object>  $rows
     * @return array<string, mixed>
     */
    private function buildSummaryFromRows(string $code, array $rows): array
    {
        $counts = [
            'total_relevant' => 0,
            'filtered_noise' => 0,
            'suspension' => 0,
            'hard_risk' => 0,
            'catalyst' => 0,
            'panic_drop' => 0,
        ];

        $events = [];
        $topEvent = null;

        foreach ($rows as $row) {
            $title = (string) ($row->title ?? '');
            $summary = $row->summary !== null ? (string) $row->summary : null;

            if (! $this->isFinanciallyRelevant($title, $code, $summary)) {
                $counts['filtered_noise']++;
                continue;
            }

            $counts['total_relevant']++;
            $cls = $this->classifyArticle(
                $title,
                $summary,
                $row->sentiment_label !== null ? (string) $row->sentiment_label : null,
                $row->sentiment_score !== null ? (float) $row->sentiment_score : null
            );

            match ($cls['tag']) {
                'SUSPENSION_ALERT' => $counts['suspension']++,
                'HARD_RISK' => $counts['hard_risk']++,
                'CATALYST' => $counts['catalyst']++,
                'PANIC_DROP' => $counts['panic_drop']++,
                default => null,
            };

            $pubDate = $row->published_at ? Carbon::parse((string) $row->published_at)->timezone('Asia/Jakarta') : null;
            $item = [
                'id' => $row->id,
                'tag' => $cls['tag'],
                'label' => $cls['label'],
                'severity' => $cls['severity'],
                'title' => $title,
                'source_url' => $row->source_url ?? null,
                'published_at' => $pubDate?->format('Y-m-d H:i'),
                'date' => $pubDate?->format('Y-m-d'),
            ];

            if ($cls['tag'] !== 'NEUTRAL' && count($events) < 8) {
                $events[] = $item;
            }

            if ($topEvent === null || $cls['severity'] > $topEvent['severity']) {
                $topEvent = $item;
            }
        }

        $badge = ($topEvent && $topEvent['tag'] !== 'NEUTRAL') ? $topEvent['tag'] : 'NONE';
        $badgeClass = match ($badge) {
            'SUSPENSION_ALERT' => 'bg-rose-600/25 text-rose-200 border-rose-500/60 font-bold',
            'HARD_RISK' => 'bg-rose-500/15 text-rose-300 border-rose-500/40 font-semibold',
            'CATALYST' => 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 font-semibold',
            'PANIC_DROP' => 'bg-amber-500/15 text-amber-300 border-amber-500/40 font-medium',
            default => 'bg-slate-800/70 text-slate-400 border-slate-700/70',
        };

        $label = match ($badge) {
            'SUSPENSION_ALERT' => '⛔ SUSPENSI / UMA',
            'HARD_RISK' => '🔴 HARD RISK',
            'CATALYST' => '🟢 CATALYST',
            'PANIC_DROP' => '🟡 PANIC DROP',
            default => $counts['total_relevant'] > 0 ? '⚪ Netral (' . $counts['total_relevant'] . ')' : '—',
        };

        return [
            'badge' => $badge,
            'label' => $label,
            'badge_class' => $badgeClass,
            'headline' => $topEvent['title'] ?? null,
            'published_at' => $topEvent['published_at'] ?? null,
            'counts' => $counts,
            'events' => $events,
        ];
    }
}
