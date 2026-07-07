<?php

namespace App\Services\News;

use App\Models\Stock;
use Illuminate\Support\Str;

class StockKeywordMapper
{
    /**
     * Override manual per kode emiten jika butuh kata kunci khusus.
     * Tambahkan sesuai kebutuhan.
     */
    protected array $overrides = [
        'BBCA' => [
            'PT Bank Central Asia Tbk',
            'PT Bank Central Asia',
            'Bank Central Asia',
            'Bank BCA',
            'saham BBCA',
            'emiten BBCA',
            'BBCA.JK',
            'BBCA',
            'BCA',
        ],
        'BBNI' => ['BBNI', 'BNI', 'Bank Negara Indonesia'],
        'BBRI' => ['BBRI', 'BRI', 'Bank Rakyat Indonesia', 'BRImo'],
        'BBTN' => ['BBTN', 'BTN', 'Bank Tabungan Negara'],
        'BMRI' => [
            'PT Bank Mandiri Persero Tbk',
            'PT Bank Mandiri',
            'Bank Mandiri',
            'saham BMRI',
            'emiten BMRI',
            'BMRI.JK',
            'BMRI',
        ],
        'MEGA' => ['MEGA', 'Bank Mega'],
        'TLKM' => ['TLKM', 'Telkom', 'Telkom Indonesia', 'PT Telkom Indonesia', 'Telkomsel', 'IndiHome', 'TelkomGroup', 'Telkomsat'],
        'ASII' => ['ASII', 'Astra', 'Astra International', 'Astra Otoparts'],
        'GOTO' => [
            'PT GoTo Gojek Tokopedia Tbk',
            'PT GoTo Gojek Tokopedia',
            'GoTo Gojek Tokopedia',
            'GoTo Group',
            'saham GOTO',
            'emiten GOTO',
            'GOTO.JK',
            'GOTO',
        ],
        'UNVR' => [
            'PT Unilever Indonesia Tbk',
            'PT Unilever Indonesia',
            'Unilever Indonesia',
            'saham UNVR',
            'emiten UNVR',
            'UNVR.JK',
            'UNVR',
        ],
        'INDF' => [
            'PT Indofood Sukses Makmur Tbk',
            'PT Indofood Sukses Makmur',
            'Indofood Sukses Makmur',
            'saham INDF',
            'emiten INDF',
            'INDF.JK',
            'INDF',
            'Indofood',
        ],
        'ICBP' => [
            'PT Indofood CBP Sukses Makmur Tbk',
            'PT Indofood CBP Sukses Makmur',
            'Indofood CBP Sukses Makmur',
            'Indofood CBP',
            'saham ICBP',
            'emiten ICBP',
            'ICBP.JK',
            'ICBP',
        ],
        'ADRO' => ['ADRO', 'Adaro', 'Adaro Energy', 'Adaro Energy Indonesia'],
        'BUMI' => ['BUMI saham', 'PT Bumi Resources', 'Bumi Resources', 'BUMI.JK', 'emiten bumi'],
        'DEWA' => ['DEWA saham', 'Darma Henwa', 'PT Darma Henwa', 'DEWA.JK'],
    ];

    /**
     * Kata kunci pengecualian per saham untuk menghindari konteks salah.
     */
    protected array $exclusions = [
        'GOTO' => ['goto islands', 'goto island', 'camellia', 'nagasaki', 'archipelago', 'tsubaki'],
        'ASII' => ['asia', 'asian', 'asii express', 'asia express', 'asia finance'],
        'DEWA' => ['dewa united', 'dewa 19', 'dewa dewi', 'dewa chord', 'dewa lirik'],
    ];

    /**
     * Kata kunci pengecualian global (promosi / riset pasar global / lifestyle) yang berlaku untuk semua saham.
     */
    protected array $globalExclusions = [
        // Promosi & merchant
        'promo', 'diskon', 'voucher', 'cashback', 'merchant',
        'pizza', 'mcdonald', 'kfc', 'resto', 'restoran', 'kuliner',
        'gratis', 'cicilan 0%', 'installment', 'belanja',
        // Job listings
        'lowongan', 'rekrutmen', 'karir', 'hiring',
        // Market research tidak relevan
        'lactic acid', 'polylactic', 'global market size',
        'cagr:', 'swot analysis', 'market research',
        // Lifestyle
        'skincare', 'fashion', 'liburan', 'wisata', 'hotel deals',
        // Entertainment/lifestyle
        'mortuary', 'shudder', 'streaming', 'watch online',
        'film', 'movie', 'series', 'drama', 'sinopsis',
        // CSR/Program non-financial
        'magang bergaji', 'lowongan magang', 'program csr',
        'berbakti', 'kkn', 'mahasiswa', 'beasiswa',
        // Sports
        'olahraga', 'sepak bola', 'bola basket', 'atletik',
        // Bencana/alam
        'gempa bumi', 'gempa', 'tsunami', 'bencana alam', 'longsor',
    ];
    /**
     * Kata kunci sektor tambahan per saham untuk memperkaya query kontekstual.
     */
    protected array $sectorKeywords = [
        'BBCA' => ['bank', 'perbankan', 'kredit', 'dpk', 'dana pihak ketiga', 'dividen', 'laba', 'rugi', 'rights issue'],
        'BBRI' => ['bank', 'perbankan', 'kredit', 'umkm', 'mikro', 'dividen', 'laba', 'rugi'],
        'BMRI' => ['bank', 'perbankan', 'kredit', 'kartu kredit', 'dividen', 'laba', 'rugi'],
        'TLKM' => ['telco', 'telekomunikasi', 'fiber', 'broadband', 'data center', 'telkomsel', 'indihome', 'laba', 'dividen'],
        'ASII' => ['otomotif', 'automotive', 'mobil', 'motor', 'penjualan mobil', 'kendaraan', 'dividen', 'laba'],
        'GOTO' => ['teknologi', 'ecommerce', 'e-commerce', 'ride hailing', 'gojek', 'tokopedia', 'rugi', 'ipo', 'gross transaction value', 'ebitda'],
        'UNVR' => ['consumer', 'consumer goods', 'fmcg', 'produk rumah tangga', 'home care', 'dividen', 'laba'],
        'INDF' => ['consumer', 'makanan', 'minuman', 'laba', 'dividen'],
        'ICBP' => ['consumer', 'makanan', 'minuman', 'mie instan', 'branded consumer', 'laba', 'dividen'],
        'ADRO' => ['batubara', 'coal', 'pertambangan', 'royalty', 'dividen', 'produksi', 'harga batu bara', 'energi'],
        'BUMI' => ['batubara', 'coal', 'pertambangan', 'harga batu bara', 'produksi', 'restrukturisasi', 'dividen'],
        'DEWA' => ['jasa pertambangan', 'kontraktor tambang', 'alat berat', 'overburden', 'batubara', 'pertambangan'],
    ];

    public function keywords(Stock $stock): array
    {
        $code = $stock->code;
        $name = $stock->company_name ?? $stock->code;

        $cleanName = trim(Str::of($name)->replace(['Tbk', 'tbk.', 'TBK', '.', ','], ' ')->squish());
        $parts = collect(explode(' ', $cleanName))
            ->filter()
            ->values();

        // Nama pendek: 2-3 kata pertama
        $short = $parts->take(3)->implode(' ');

        $aliases = collect([$code, $cleanName, $short])
            ->filter()
            ->unique()
            ->values()
            ->all();

        if (array_key_exists($code, $this->overrides)) {
            $aliases = array_values(array_unique(array_merge($this->overrides[$code], $aliases)));
        }

        return $aliases;
    }

    public function exclusionKeywords(Stock $stock): array
    {
        $perStock = $this->exclusions[$stock->code] ?? [];
        return array_values(array_unique(array_merge($this->globalExclusions, $perStock)));
    }

    public function queryString(Stock $stock): string
    {
        $keywords = $this->searchAliases($stock, 0);
        return collect($keywords)->map(fn ($k) => "\"{$k}\"")->implode(' OR ');
    }

    public function contextualQuery(Stock $stock, ?array $context = null): string
    {
        $ctx = $context ?? config('news.context_keywords', []);
        $left = '(' . $this->queryString($stock) . ')';
        $rightParts = [];

        if ($ctx && count($ctx)) {
            $rightParts[] = '(' . collect($ctx)->map(function ($w) {
                $w = trim($w);
                return $w ? "\"{$w}\"" : null;
            })->filter()->implode(' OR ') . ')';
        }

        $sectorCtx = $this->sectorKeywords[$stock->code] ?? [];
        if ($sectorCtx) {
            $rightParts[] = '(' . collect($sectorCtx)->map(function ($w) {
                $w = trim($w);
                return $w ? "\"{$w}\"" : null;
            })->filter()->implode(' OR ') . ')';
        }

        $right = '';
        if ($rightParts) {
            $right = ' AND (' . implode(' OR ', $rightParts) . ')';
        }

        return trim($left . $right);
    }

    /**
     * Berikan akses sektor keywords untuk builder luar jika perlu.
     */
    public function sectorKeywords(Stock $stock): array
    {
        return $this->sectorKeywords[$stock->code] ?? [];
    }

    /**
     * Prioritaskan nama legal emiten dan frasa ticker-specific untuk query provider.
     */
    public function searchAliases(Stock $stock, int $limit = 6): array
    {
        $cleanName = trim((string) Str::of($stock->company_name ?? $stock->code)
            ->replace(['Tbk', 'tbk.', 'TBK', '.', ','], ' ')
            ->squish());

        $aliases = collect($this->keywords($stock))
            ->filter(fn ($alias) => trim((string) $alias) !== '')
            ->unique()
            ->sortByDesc(function ($alias) use ($stock, $cleanName) {
                $alias = trim((string) $alias);
                $aliasLower = mb_strtolower($alias);
                $score = 0;

                if ($aliasLower === mb_strtolower($cleanName)) {
                    $score += 300;
                }
                if (str_contains($aliasLower, 'pt ')) {
                    $score += 220;
                }
                if (str_contains($aliasLower, mb_strtolower($stock->code))) {
                    $score += 160;
                }
                if (str_contains($aliasLower, 'saham ') || str_contains($aliasLower, 'emiten ')) {
                    $score += 120;
                }
                if (str_contains($alias, ' ')) {
                    $score += 60;
                }

                return $score + min(40, mb_strlen($alias));
            })
            ->values();

        if ($limit <= 0) {
            return $aliases->all();
        }

        return $aliases->take($limit)->all();
    }

    public function globalExclusions(): array
    {
        return $this->globalExclusions;
    }

    public function primarySearchAlias(Stock $stock): string
    {
        return (string) ($this->searchAliases($stock, 1)[0] ?? $stock->company_name ?? $stock->code);
    }

    /**
     * Query pendek dan exact untuk provider search/scraper.
     *
     * @return array<int, string>
     */
    public function exactSearchQueries(Stock $stock, int $limit = 5): array
    {
        $tickerQueries = collect([
            'saham '.$stock->code,
            'emiten '.$stock->code,
        ]);

        $issuerAliases = collect($this->searchAliases($stock, 10))
            ->reject(function ($alias) use ($stock, $tickerQueries) {
                $alias = trim((string) $alias);
                $normalized = mb_strtolower($alias);

                if ($tickerQueries->contains($alias)) {
                    return true;
                }

                if ($normalized === mb_strtolower($stock->code) || $normalized === mb_strtolower($stock->code.'.JK')) {
                    return true;
                }

                return ! str_contains($alias, ' ');
            })
            ->values();

        $queries = $issuerAliases
            ->merge($tickerQueries)
            ->filter(fn ($query) => trim((string) $query) !== '')
            ->unique()
            ->values();

        if ($limit > 0) {
            return $queries->take($limit)->all();
        }

        return $queries->all();
    }

    public function directHits(Stock $stock, ?string $text): array
    {
        return $this->matchKeywords($text, $this->keywords($stock));
    }

    public function competingIssuerHits(Stock $stock, ?string $text): array
    {
        $haystack = mb_strtolower((string) $text);
        if ($haystack === '') {
            return [];
        }

        $hits = [];
        foreach ($this->issuerKeywordMap($stock->code) as $keyword => $code) {
            $keyword = trim($keyword);
            if ($keyword === '') {
                continue;
            }

            if (str_contains($haystack, mb_strtolower($keyword))) {
                $hits[$code][] = $keyword;
            }
        }

        return collect($hits)
            ->map(fn ($keywords) => array_values(array_unique($keywords)))
            ->all();
    }

    public function issuerKeywordMap(?string $excludeCode = null): array
    {
        $map = [];

        foreach ($this->overrides as $code => $keywords) {
            if ($excludeCode && strtoupper($excludeCode) === $code) {
                continue;
            }

            foreach (array_merge([$code], $keywords) as $keyword) {
                $keyword = trim((string) $keyword);
                if ($keyword === '' || mb_strlen($keyword) < 3) {
                    continue;
                }

                $map[$keyword] = $code;
            }
        }

        return $map;
    }

    /**
     * Kode ticker yang juga kata umum Bahasa Indonesia (bumi = tanah/planet, dewa = tuhan/idiom
     * "tingkat dewa"). Substring match biasa akan salah tangkap "Dewan"/"Sadewa" (mengandung "dewa")
     * atau berita geografi/sains yang menyebut "Bumi". Untuk kode-kode ini, bare code wajib cocok
     * case-sensitive dan sebagai kata utuh (bukan bagian dari kata lain).
     */
    protected array $ambiguousCommonWordCodes = ['BUMI', 'DEWA'];

    /**
     * Whether a single keyword matches inside the ORIGINAL-case text. Ambiguous common-word codes
     * (BUMI, DEWA) require a case-sensitive, whole-word match; every other keyword keeps the
     * existing case-insensitive substring match. Callers that only have lowercased text (e.g. for
     * unrelated case-insensitive comparisons) must pass the original-case text here, not a
     * pre-lowercased copy, or the ambiguous-code check can never succeed.
     */
    public function keywordMatches(string $keyword, string $originalText): bool
    {
        $keyword = trim($keyword);
        if ($keyword === '' || $originalText === '') {
            return false;
        }

        if (in_array($keyword, $this->ambiguousCommonWordCodes, true)) {
            return (bool) preg_match('/\b'.preg_quote($keyword, '/').'\b/', $originalText);
        }

        // Single-token keywords (bare ticker codes, no space) risk matching as a substring inside an
        // unrelated longer word -- e.g. "GOTO" inside "ngotot" (insist), "MEGA" inside "Megawati" or
        // "megaproyek", "BRI" inside "hibrida". Require a word boundary for these (still
        // case-insensitive, since the ticker's own casing style varies e.g. "GoTo" vs "GOTO").
        // Multi-word phrases (e.g. "Bumi Resources", "GoTo Gojek Tokopedia") are specific enough that
        // a plain substring match stays safe.
        if (! str_contains($keyword, ' ')) {
            return (bool) preg_match('/\b'.preg_quote($keyword, '/').'\b/iu', $originalText);
        }

        return str_contains(mb_strtolower($originalText), mb_strtolower($keyword));
    }

    protected function matchKeywords(?string $text, array $keywords): array
    {
        $original = (string) $text;
        if ($original === '') {
            return [];
        }

        return collect($keywords)
            ->filter(fn ($keyword) => $this->keywordMatches((string) $keyword, $original))
            ->unique()
            ->values()
            ->all();
    }
}
