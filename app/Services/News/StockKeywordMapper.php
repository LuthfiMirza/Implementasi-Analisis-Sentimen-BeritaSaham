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
        'BBCA' => ['BBCA', 'BCA', 'Bank Central Asia', 'BCA Digital', 'BCA Finance'],
        'BBRI' => ['BBRI', 'BRI', 'Bank Rakyat Indonesia'],
        'BMRI' => ['BMRI', 'Bank Mandiri', 'Mandiri'],
        'TLKM' => ['TLKM', 'Telkom', 'Telkom Indonesia', 'PT Telkom Indonesia', 'Telkomsel', 'IndiHome'],
        'ASII' => ['ASII', 'Astra', 'Astra International', 'Astra Otoparts'],
        'GOTO' => ['GOTO', 'GoTo Group', 'GoTo Gojek Tokopedia', 'Gojek', 'Tokopedia', 'PT GoTo Gojek Tokopedia'],
        'UNVR' => ['UNVR', 'Unilever Indonesia'],
        'INDF' => ['INDF', 'Indofood', 'Indofood Sukses Makmur'],
        'ICBP' => ['ICBP', 'Indofood CBP'],
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
        'UNVR' => ['consumer', 'fmcg', 'produk rumah tangga', 'dividen', 'laba'],
        'INDF' => ['consumer', 'makanan', 'minuman', 'laba', 'dividen'],
        'ICBP' => ['consumer', 'makanan', 'minuman', 'laba', 'dividen'],
        'ADRO' => ['batubara', 'coal', 'pertambangan', 'royalty', 'dividen', 'produksi', 'harga batu bara', 'energi'],
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
        $keywords = $this->keywords($stock);
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

    public function globalExclusions(): array
    {
        return $this->globalExclusions;
    }
}
